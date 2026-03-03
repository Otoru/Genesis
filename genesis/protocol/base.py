"""
Genesis Protocol Base Class
----------------------------

Base Protocol class for ESL (Event Socket Layer) communication.
Handles common functionality for inbound and outbound connections.
"""

import asyncio
from asyncio import (
    iscoroutinefunction,
    StreamWriter,
    StreamReader,
    create_task,
    to_thread,
    Event,
    Queue,
    Task,
    CancelledError,
)
from typing import List, Dict, Optional, Callable, Coroutine, Any, Union, cast
from abc import ABC
import time

from opentelemetry import trace

from genesis.exceptions import ConnectionError, UnconnectedError
from genesis.observability import logger, TRACE_LEVEL_NUM
from genesis.protocol.parser import ESLEvent, parse_headers
from genesis.protocol.reader_fsm import ESLReaderFSM
from genesis.protocol.metrics import (
    tracer,
    commands_sent_counter,
    events_received_counter,
    command_duration_histogram,
    command_errors_counter,
    channel_operations_counter,
    channel_operation_duration,
    hangup_causes_counter,
    bridge_operations_counter,
    dtmf_received_counter,
    call_duration_histogram,
    timeout_counter,
    channel_routing_counter,
    global_routing_counter,
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
from genesis.types import EventHandler


class Protocol(ABC):
    def __init__(self):
        self.events: Queue[ESLEvent] = Queue()
        self.commands: Queue[ESLEvent] = Queue()
        self.is_connected = False
        self.is_lingering = False
        self.authentication_event = Event()
        self.producer: Optional[Task] = None
        self.consumer: Optional[Task] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.handlers: Dict[str, List[EventHandler]] = {}
        self.channel_registry: Dict[str, List[EventHandler]] = {}

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
        if self.writer and not self.writer.is_closing():
            logger.debug("Closer stream writer.")
            self.writer.close()

        self.is_connected = False
        await self._cancel_task(self.producer, "event producer")
        await self._cancel_task(self.consumer, "event consumer")

    async def _cancel_task(
        self, task: Optional[Task[Any]], label: str = "task"
    ) -> None:
        """Cancel a task and wait for it; swallow CancelledError."""
        if task is None or task.cancelled():
            return
        logger.debug(f"Cancel {label} task.")
        task.cancel()
        try:
            await task
        except (Exception, CancelledError):
            pass

    async def handler(self) -> None:
        """Defines intelligence to treat received events (state machine driven)."""
        if self.reader is None:
            return

        fsm = ESLReaderFSM()

        while self.is_connected:
            # State: READING_HEADERS — accumulate until end of header block
            request: Optional[str] = None
            buffer = ""

            while self.is_connected:
                try:
                    content = await self.reader.readline()
                    if not content:
                        self.is_connected = False
                        break
                    buffer += content.decode("utf-8")
                except Exception as e:
                    logger.error(f"Error reading from stream. {str(e)}")
                    self.is_connected = False
                    break

                if buffer.endswith("\n\n") or buffer.endswith("\r\n\r\n"):
                    request = buffer
                    logger.trace(f"Complete message received: {repr(request)}")
                    break

            if not request or not self.is_connected:
                break

            events_from_headers, content_length = fsm.process_headers(request)

            for ev in events_from_headers:
                await self.events.put(ev)

            if content_length > 0:
                logger.trace(f"Total content length: {content_length} bytes")
                try:
                    data = await self.reader.readexactly(content_length)
                except Exception as e:
                    logger.error(f"Error reading body: {str(e)}")
                    self.is_connected = False
                    break
                body_events = fsm.process_body(data)
                for ev in body_events:
                    await self.events.put(ev)

    async def consume(self) -> None:
        """Arm all event processors."""
        while self.is_connected:
            event = await self.events.get()
            try:
                await self._process_one_event(event)
            except Exception as outer_e:
                logger.error(f"Error in consumer loop: {outer_e}", exc_info=True)

    async def _process_one_event(self, event: ESLEvent) -> None:
        """Run telemetry, processors, and dispatch for one event."""
        try:
            attributes = build_event_attributes(event)
            with tracer.start_as_current_span("process_event", attributes=attributes):
                record_event_metrics(event)
                log_event(event)
        except Exception:
            record_event_metrics(event)
            log_event(event)

        for processor in self.event_processors:
            result = processor(self, event)
            if asyncio.iscoroutine(result):
                await result

        handlers, _ = await self.routing_strategy.route(event)
        if handlers:
            dispatch_to_handlers(handlers, event)

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
            raise UnconnectedError()

        if self.writer.is_closing():
            raise ConnectionError()

        command_name = cmd.split()[0] if cmd.strip() else ""
        start_time = time.perf_counter()

        try:
            with tracer.start_as_current_span("send_command") as span:
                span.set_attribute("command.name", cmd)
                return await self._execute_send(cmd, command_name, start_time, span)
        except Exception:
            # OTel not initialized - run without tracing
            return await self._execute_send(cmd, command_name, start_time, None)

    def _record_command_error(self, command_name: str, error: str) -> None:
        """Record command error metric (best-effort)."""
        if not command_name:
            return
        try:
            command_errors_counter.add(
                1, attributes={"command": command_name, "error": error}
            )
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
        try:
            if command_name:
                commands_sent_counter.add(1, attributes={"command": command_name})
        except Exception:
            pass

        try:
            if self.writer is None:
                raise UnconnectedError()
            self.writer.write(f"{cmd}\n\n".encode())
            await self.writer.drain()
            result = await self.commands.get()

            reply = result.get("Reply-Text", "")
            if reply.startswith("-ERR"):
                self._record_command_error(command_name, "protocol_error")

            if span is not None:
                reply_text = result.get("Reply-Text")
                if reply_text:
                    span.set_attribute("command.reply", reply_text)

            return result
        except Exception as e:
            self._record_command_error(command_name, type(e).__name__)
            raise
        finally:
            if command_name:
                try:
                    duration = time.perf_counter() - start_time
                    command_duration_histogram.record(
                        duration, attributes={"command": command_name}
                    )
                except Exception:
                    pass
