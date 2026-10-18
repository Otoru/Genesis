"""
Genesis Protocol Base Class
----------------------------

Base Protocol class for ESL (Event Socket Layer) communication.
Handles common functionality for inbound and outbound connections.
"""

import asyncio
from asyncio import (
    IncompleteReadError,
    StreamWriter,
    StreamReader,
    create_task,
    current_task,
    Event,
    Queue,
    Task,
    CancelledError,
)
from typing import List, Dict, Optional, Any
from abc import ABC
import time

from opentelemetry import trace

from genesis.exceptions import (
    CommandStage,
    ConnectionError,
    ConnectionLost,
    GenesisError,
    UnconnectedError,
)
from genesis.observability import logger
from genesis.protocol.exchange import CommandExchange, WriteEvidence
from genesis.protocol.parser import ESLEvent
from genesis.protocol.reader_fsm import ESLReaderFSM
from genesis.protocol.metrics import (
    tracer,
    commands_sent_counter,
    command_duration_histogram,
    command_errors_counter,
    event_processing_duration,
    connection_errors_counter,
    register_protocol,
    safe_add,
    safe_record,
    ObservingSpan,
)
from genesis.protocol.routing import (
    CompositeRoutingStrategy,
    ChannelRoutingStrategy,
    GlobalRoutingStrategy,
    dispatch_to_handlers,
)
from genesis.protocol.telemetry import (
    build_event_attributes,
    record_event_metrics,
    log_event,
)
from genesis.protocol.processors import default_processors
from genesis.protocol.subscriptions import SubscriptionLedger
from genesis.types import EventHandler


class Protocol(ABC):
    def __init__(self):
        self.events: Queue[Optional[ESLEvent]] = Queue()
        self.exchange = CommandExchange(self._flush_queued_events)
        self.is_connected = False
        self.is_lingering = False
        self.authentication_event = Event()
        self._closed = Event()
        self._lost = False
        self._stopped = False
        self._reader_signaled = False
        self._pending_loss_reason: Optional[str] = None
        self.producer: Optional[Task] = None
        self.consumer: Optional[Task] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.handlers: Dict[str, List[EventHandler]] = {}
        self.channel_registry: Dict[str, List[EventHandler]] = {}
        self.handler_tasks: set[Task[Any]] = set()
        self.subscriptions = SubscriptionLedger()
        # Register so the ObservableGauges can report this protocol's queue depth.
        register_protocol(self)

        # Initialize routing strategy (Strategy Pattern)
        self.routing_strategy = CompositeRoutingStrategy(
            [
                ChannelRoutingStrategy(self.channel_registry),  # O(1) routing first
                GlobalRoutingStrategy(self.handlers),  # O(N) fallback
            ]
        )
        # Event processors (adapters) run before routing; extend for use-case logic
        self.event_processors = default_processors()

    async def start(self) -> None:
        """Initiates a connection to a freeswitch (starts producer/consumer tasks)."""
        self.is_connected = True

        logger.debug("Create tasks to work with ESL events.")
        self.producer = create_task(self.handler())
        self.consumer = create_task(self.consume())

    async def stop(self) -> None:
        """Terminates connection to a freeswitch."""
        if self._stopped:
            return
        self._stopped = True
        self.is_connected = False
        self.authentication_event.set()
        self.exchange.fail_pending()

        if self.writer is not None and not self.writer.is_closing():
            logger.debug("Closer stream writer.")
            self.writer.close()

        await self._settle_handlers()
        self._closed.set()

        current = current_task()
        await self._cancel_unless(self.producer, current, "event producer")
        await self._cancel_unless(self.consumer, current, "event consumer")
        for task in list(self.handler_tasks):
            await self._cancel_unless(task, current, "handler task")
        self.handler_tasks.clear()

    def raise_if_lost(self, stage: CommandStage) -> None:
        """Raise ``ConnectionLost(stage)`` when this connection is already closed."""
        if self._closed.is_set():
            raise ConnectionLost(stage)

    async def wait_lost(self, stage: CommandStage) -> None:
        """Wait until this connection closes, then raise ``ConnectionLost(stage)``.

        The caller supplies ``stage``. ``ACCEPTED`` is for a wait that already
        observed the command reply. A local ``stop()`` closes the connection too.
        """
        await self._closed.wait()
        raise ConnectionLost(stage)

    def note_peer_loss(self, reason: str) -> None:
        """Mark the peer gone. Queued events still run before ``wait_lost``."""
        if self._lost:
            return
        self._lost = True
        self.is_connected = False
        self.exchange.close()
        safe_add(
            connection_errors_counter,
            1,
            attributes={"error": reason, "type": "esl"},
        )
        self.authentication_event.set()

    async def _flush_queued_events(self) -> None:
        """Let the consumer deliver events already queued. No new socket read."""
        turns = self.events.qsize() + 1
        for _ in range(turns):
            await asyncio.sleep(0)

    async def _settle_handlers(self) -> None:
        """One turn for handlers already scheduled. Does not wait past their first await."""
        if not any(not task.done() for task in self.handler_tasks):
            return
        await asyncio.sleep(0)

    async def _cancel_unless(
        self,
        task: Optional[Task[Any]],
        current: Optional[Task[Any]],
        label: str,
    ) -> None:
        """Cancel ``task`` unless it is the caller. ``stop()`` must not await itself."""
        if task is None or task is current:
            return
        await self._cancel_task(task, label)

    async def _cancel_task(
        self, task: Optional[Task[Any]], label: str = "task"
    ) -> None:
        """Cancel a task and wait for it; swallow CancelledError."""
        if task is None:
            return
        if task.done():
            try:
                await task
            except (Exception, CancelledError):
                pass
            return
        logger.debug(f"Cancel {label} task.")
        task.cancel()
        try:
            await task
        except (Exception, CancelledError):
            pass

    async def _read_header_block(self) -> Optional[str]:
        """Read lines from self.reader until a complete header block is received.

        Accumulates lines into a buffer until the block ends with ``\\n\\n`` or
        ``\\r\\n\\r\\n``.  Sets ``self.is_connected = False`` on EOF or any I/O
        error and returns ``None`` in those cases.
        """
        buffer = ""
        while self.is_connected:
            try:
                content = await self.reader.readline()  # type: ignore[union-attr]
            except CancelledError:
                raise
            except IncompleteReadError:
                self._pending_loss_reason = "truncated"
                self.is_connected = False
                return None
            except Exception as e:
                logger.error(f"Error reading from stream. {str(e)}")
                self._pending_loss_reason = "eof"
                self.is_connected = False
                return None

            if not content:
                self._pending_loss_reason = "truncated" if buffer else "eof"
                self.is_connected = False
                return None
            buffer += content.decode("utf-8")

            if buffer.endswith("\n\n") or buffer.endswith("\r\n\r\n"):
                logger.trace(f"Complete message received: {repr(buffer)}")
                return buffer

        return None

    async def _read_body_bytes(self, content_length: int) -> Optional[bytes]:
        """Read exactly *content_length* bytes from self.reader.

        Sets ``self.is_connected = False`` on any I/O error and returns ``None``
        in that case.
        """
        try:
            return await self.reader.readexactly(content_length)  # type: ignore[union-attr]
        except CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error reading body: {str(e)}")
            self._pending_loss_reason = "truncated"
            self.is_connected = False
            return None

    async def handler(self) -> None:
        """Defines intelligence to treat received events (state machine driven)."""
        if self.reader is None:
            return

        fsm = ESLReaderFSM()
        try:
            while self.is_connected:
                # State: READING_HEADERS — accumulate until end of header block
                request = await self._read_header_block()

                if not request or not self.is_connected:
                    break

                events_from_headers, content_length = fsm.process_headers(request)

                for ev in events_from_headers:
                    await self.events.put(ev)

                if content_length > 0:
                    logger.trace(f"Total content length: {content_length} bytes")
                    data = await self._read_body_bytes(content_length)
                    if data is None:
                        break
                    body_events = fsm.process_body(data)
                    for ev in body_events:
                        await self.events.put(ev)
        except CancelledError:
            raise
        finally:
            await self._signal_reader_done()

    async def _signal_reader_done(self) -> None:
        """After the reader stops, let the consumer drain events already queued."""
        if self._stopped or self._reader_signaled:
            return
        reason = self._pending_loss_reason
        if reason is None:
            return
        self._reader_signaled = True
        self.note_peer_loss(reason)
        await self.events.put(None)

    async def consume(self) -> None:
        """Arm all event processors."""
        while not self._stopped:
            event = await self.events.get()
            if event is None:
                await self.stop()
                return
            try:
                await self._process_one_event(event)
            except Exception as outer_e:
                logger.error(f"Error in consumer loop: {outer_e}", exc_info=True)

    async def _process_one_event(self, event: ESLEvent) -> None:
        """Run telemetry, processors, and dispatch for one event.

        The ``process_event`` span wraps metrics+logging AND the processor
        chain + routing, so the new ``freeswitch.channel.*`` lifecycle spans
        (emitted by processors) become children of it and share its trace.
        """
        try:
            attributes = build_event_attributes(event)
        except Exception:
            attributes = {}

        start_time = time.perf_counter()
        opened = ObservingSpan.open("process_event", attributes)
        try:
            try:
                record_event_metrics(event)
            except Exception:
                pass
            try:
                log_event(event)
            except Exception:
                pass

            for processor in list(self.event_processors):
                try:
                    result = processor(self, event)
                    if asyncio.iscoroutine(result):
                        await result
                except CancelledError:
                    raise
                except Exception:
                    logger.debug("event processor failed")

            handlers, _ = await self.routing_strategy.route(event)
            if handlers:
                dispatch_to_handlers(handlers, event, self.handler_tasks)
        finally:
            opened.close()

        safe_record(
            event_processing_duration,
            time.perf_counter() - start_time,
            attributes={
                "event.name": event.get("Event-Name", "UNKNOWN"),
            },
        )

    def on(
        self,
        key: str,
        handler: Any,
    ) -> None:
        """Associate a handler with an event key."""
        logger.debug(f"Register handler to '{key}' event.")
        self.handlers.setdefault(key, []).append(handler)

    def remove(
        self,
        key: str,
        handler: Any,
    ) -> None:
        """Removes the HANDLER from the list of handlers for the given event KEY name."""
        logger.debug(f"Remove handler to '{key}' event.")
        if key in self.handlers and handler in self.handlers[key]:
            self.handlers[key].remove(handler)

    def register_channel_handler(
        self,
        uuid: str,
        event_name: str,
        handler: EventHandler,
    ) -> None:
        """Register a handler for a specific channel UUID.

        This provides O(1) event routing for channel-specific events instead of
        the O(N) iteration through all handlers.

        Args:
            uuid: The Unique-ID of the channel
            event_name: The event name to listen for (e.g., "CHANNEL_STATE")
            handler: The handler function to call when the event occurs
        """
        key = f"{uuid}:{event_name}"
        logger.debug(f"Register channel handler for '{key}'")
        self.channel_registry.setdefault(key, []).append(handler)

    def unregister_channel_handler(
        self,
        uuid: str,
        event_name: str,
        handler: EventHandler,
    ) -> None:
        """Unregister a channel-specific handler.

        Args:
            uuid: The Unique-ID of the channel
            event_name: The event name
            handler: The handler function to remove
        """
        key = f"{uuid}:{event_name}"
        logger.debug(f"Unregister channel handler for '{key}'")
        if key in self.channel_registry:
            if handler in self.channel_registry[key]:
                self.channel_registry[key].remove(handler)
                # Clean up empty lists to avoid memory leaks
                if not self.channel_registry[key]:
                    del self.channel_registry[key]

    async def send(self, cmd: str) -> ESLEvent:
        """Method used to send commands to or freeswitch."""
        if not self.is_connected or self.writer is None:
            if self._lost:
                raise ConnectionLost(CommandStage.NOT_SENT)
            raise UnconnectedError()

        if self.writer.is_closing():
            raise ConnectionError()

        command_name = cmd.split()[0] if cmd.strip() else ""
        start_time = time.perf_counter()
        opened = _CommandSpan.open(command_name, cmd)
        try:
            return await self._execute_send(cmd, command_name, start_time, opened.span)
        finally:
            opened.close()

    def _record_command_error(
        self,
        command_name: str,
        error: str,
        stage: Optional[CommandStage] = None,
    ) -> None:
        """Record command error metric (best-effort)."""
        if not command_name:
            return
        attributes: Dict[str, str] = {"command": command_name, "error": error}
        if stage is not None:
            attributes["stage"] = stage.value
        safe_add(command_errors_counter, 1, attributes=attributes)

    def _observe_lost(
        self, command_name: str, span: Optional[Any], exc: ConnectionLost
    ) -> None:
        self._record_command_error(command_name, "connection_lost", exc.stage)
        if span is None:
            return
        try:
            span.set_attribute("command.observation", exc.stage.value)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
        except Exception:
            pass

    def _annotate_reply(
        self, result: ESLEvent, command_name: str, span: Optional[Any]
    ) -> None:
        reply = result.get("Reply-Text", "")
        if isinstance(reply, str) and reply.startswith("-ERR"):
            self._record_command_error(command_name, "protocol_error")
            if span is not None:
                try:
                    span.set_attribute("command.error", "protocol_error")
                    span.set_status(trace.Status(trace.StatusCode.ERROR, reply))
                    span.record_exception(GenesisError(reply))
                except Exception:
                    pass

        if span is None:
            return
        reply_text = result.get("Reply-Text")
        if not reply_text:
            return
        try:
            span.set_attribute("command.reply", reply_text)
        except Exception:
            pass

    async def _execute_send(
        self,
        cmd: str,
        command_name: str,
        start_time: float,
        span: Optional[Any],
    ) -> ESLEvent:
        """Execute command over the wire and record metrics (single implementation)."""
        logger.debug(f"Send command: {cmd}")

        async def transmit(evidence: WriteEvidence) -> None:
            writer = self.writer
            if writer is None:
                raise UnconnectedError()
            evidence.wrote = True
            writer.write(f"{cmd}\n\n".encode())
            if command_name:
                safe_add(commands_sent_counter, 1, attributes={"command": command_name})
            await writer.drain()

        try:
            result = await self.exchange.exchange(transmit)
        except ConnectionLost as exc:
            self._observe_lost(command_name, span, exc)
            if exc.stage is CommandStage.UNCONFIRMED and not self._stopped:
                if not self._lost:
                    self.note_peer_loss("write_error")
                await self.stop()
            raise
        except Exception as exc:
            self._record_command_error(command_name, type(exc).__name__)
            raise
        else:
            failure = self.exchange.take_write_failure()
            self._annotate_reply(result, command_name, span)
            self.subscriptions.observe(cmd, result)
            if failure is not None and not self._stopped:
                if not self._lost:
                    self.note_peer_loss("write_error")
                try:
                    await self.stop()
                except Exception:
                    logger.error("Failed to stop after a recovered ESL reply.")
            return result
        finally:
            if command_name:
                safe_record(
                    command_duration_histogram,
                    time.perf_counter() - start_time,
                    attributes={"command": command_name},
                )


class _CommandSpan:
    """Send span that cannot cause a second write."""

    def __init__(self) -> None:
        self.span: Optional[Any] = None
        self._context: Optional[Any] = None

    @classmethod
    def open(cls, command_name: str, cmd: str) -> "_CommandSpan":
        opened = cls()
        try:
            opened._context = tracer.start_as_current_span("send_command")
            opened.span = opened._context.__enter__()
        except Exception:
            opened._context = None
            opened.span = None
            return opened
        try:
            if opened.span is not None:
                # Command verb only: the raw command may carry UUIDs.
                opened.span.set_attribute("command.name", command_name)
                remainder = cmd[len(command_name) :].strip()
                if remainder:
                    opened.span.set_attribute("command.args", remainder[:200])
        except Exception:
            pass
        return opened

    def close(self) -> None:
        context = self._context
        self._context = None
        if context is None:
            return
        try:
            context.__exit__(None, None, None)
        except Exception:
            pass
