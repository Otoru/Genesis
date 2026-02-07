"""
Genesis Protocol Base Class
----------------------------

Base Protocol class for ESL (Event Socket Layer) communication.
Handles common functionality for inbound and outbound connections.
"""

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
import logging
import time

from opentelemetry import trace

from genesis.exceptions import ConnectionError, UnconnectedError
from genesis.observability import logger, TRACE_LEVEL_NUM
from genesis.protocol.parser import ESLEvent, parse_headers
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

    async def start(self) -> None:
        """Initiates a connection to a freeswitch."""
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

        if self.producer and not self.producer.cancelled():
            logger.debug("Cancel event producer task.")
            self.producer.cancel()
            try:
                await self.producer
            except (Exception, CancelledError):
                pass

        if self.consumer and not self.consumer.cancelled():
            logger.debug("Cancel event consumer task.")
            self.consumer.cancel()
            try:
                await self.consumer
            except (Exception, CancelledError):
                pass

    async def handler(self) -> None:
        """Defines intelligence to treat received events."""
        while self.is_connected:
            if self.reader is None:
                break
            request = None
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

                if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                    request = buffer
                    logger.trace(f"Complete message received: {repr(request)}")
                    break

            if not request or not self.is_connected:
                break

            event = parse_headers(request)

            if "Content-Length" in event:
                # Get the total length from the first Content-Length header
                length = int(event["Content-Length"].split("\n")[0])
                logger.trace(f"Total content length: {length} bytes")

                # Read the complete data
                data = await self.reader.readexactly(length)
                logger.trace(f"Received complete data: {data!r}")
                complete_content = data.decode("utf-8")
                contentType = event.get("Content-Type", None)

                if contentType:
                    logger.trace(f"Check content type of event: {event}")

                    if contentType not in [
                        "api/response",
                        "text/rude-rejection",
                        "log/data",
                    ]:
                        # Try to split headers and body
                        if "\n\n" in complete_content:
                            headers_part, body = complete_content.split("\n\n", 1)

                            # Here we check for multiple events in one message (can happen if event-lock is set)
                            event_parts = []

                            if "event-lock: true" in headers_part.lower():
                                # Split the string on "Event-Name: "
                                parts = headers_part.split("\nEvent-Name: ")

                                if len(parts) > 1:
                                    event_parts = [parts[0]]

                                    for part in parts[1:]:
                                        event_parts.append(f"Event-Name: {part}")

                                    logger.debug(
                                        f"Split locked event into {len(event_parts)} separate events"
                                    )
                            else:
                                event_parts = [headers_part]

                            # Process each event part
                            for idx, event_str in enumerate(event_parts):
                                if idx == 0:
                                    # First event is the original event
                                    additional_headers = parse_headers(event_str)
                                    event.update(additional_headers)
                                    event.body = body
                                    await self.events.put(event)
                                else:
                                    # More events are new events
                                    new_event = parse_headers(event_str)
                                    # Copy some headers from the original event
                                    for key in ["Content-Length", "Content-Type"]:
                                        if key in event:
                                            new_event[key] = event[key]
                                    new_event.body = body
                                    await self.events.put(new_event)
                            continue  # Skip the final event.put

                        else:
                            if contentType == "text/event-plain":
                                additional_headers = parse_headers(complete_content)
                                event.update(additional_headers)
                                event.body = ""
                                await self.events.put(event)
                                continue

                            event.body = complete_content
                    else:
                        event.body = complete_content
                else:
                    event.body = complete_content

            await self.events.put(event)

    async def consume(self) -> None:
        """Arm all event processors."""
        while self.is_connected:
            event = await self.events.get()

            try:
                # Telemetry and logging
                try:
                    attributes = build_event_attributes(event)
                    with tracer.start_as_current_span(
                        "process_event", attributes=attributes
                    ):
                        record_event_metrics(event)
                        log_event(event)
                except Exception:
                    # OTel not initialized - continue without tracing
                    record_event_metrics(event)
                    log_event(event)

                # Handle special event types
                if "Content-Type" in event and event["Content-Type"] == "auth/request":
                    self.authentication_event.set()

                elif (
                    "Content-Type" in event and event["Content-Type"] == "command/reply"
                ):
                    await self.commands.put(event)

                elif (
                    "Content-Type" in event and event["Content-Type"] == "api/response"
                ):
                    await self.commands.put(event)

                elif "Content-Type" in event and event["Content-Type"] in [
                    "text/rude-rejection",
                    "text/disconnect-notice",
                ]:
                    if not (
                        "Content-Disposition" in event
                        and event["Content-Disposition"] == "linger"
                    ):
                        await self.stop()

                # Route to event handlers using Strategy Pattern
                handlers, _ = await self.routing_strategy.route(event)

                if handlers:
                    await dispatch_to_handlers(handlers, event)

            except Exception as outer_e:
                logger.error(f"Error in consumer loop: {outer_e}", exc_info=True)
                # Continue loop to avoid freezing connection

    def on(
        self,
        key: str,
        handler: Any,
    ) -> None:
        """Associate a handler with an event key."""
        logger.debug(f"Register handler to '{key}' event.")
        self.handlers.setdefault(key, list()).append(handler)

    def remove(
        self,
        key: str,
        handler: Any,
    ) -> None:
        """Removes the HANDLER from the list of handlers for the given event KEY name."""
        logger.debug(f"Remove handler to '{key}' event.")
        if key in self.handlers and handler in self.handlers[key]:
            self.handlers.setdefault(key, list()).remove(handler)

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

        start_time = time.perf_counter()
        try:
            with tracer.start_as_current_span("send_command") as span:
                span.set_attribute("command.name", cmd)
                logger.debug(f"Send command: {cmd}")
                try:
                    command_name = cmd.split()[0]
                    commands_sent_counter.add(1, attributes={"command": command_name})
                except Exception:
                    pass

                try:
                    self.writer.write(f"{cmd}\n\n".encode())
                    await self.writer.drain()
                    result = await self.commands.get()

                    reply = result.get("Reply-Text", "")
                    if reply.startswith("-ERR"):
                        try:
                            command_errors_counter.add(
                                1,
                                attributes={
                                    "command": command_name,
                                    "error": "protocol_error",
                                },
                            )
                        except Exception:
                            pass

                    reply_text = result.get("Reply-Text")
                    if reply_text:
                        span.set_attribute("command.reply", reply_text)

                    return result
                except Exception as e:
                    try:
                        command_errors_counter.add(
                            1,
                            attributes={
                                "command": command_name,
                                "error": type(e).__name__,
                            },
                        )
                    except Exception:
                        pass
                    raise
                finally:
                    try:
                        duration = time.perf_counter() - start_time
                        command_duration_histogram.record(
                            duration, attributes={"command": command_name}
                        )
                    except Exception:
                        pass
        except Exception:
            # OTel not initialized - run without tracing
            logger.debug(f"Send command: {cmd}")
            try:
                command_name = cmd.split()[0]
                commands_sent_counter.add(1, attributes={"command": command_name})
            except Exception:
                pass

            try:
                self.writer.write(f"{cmd}\n\n".encode())
                await self.writer.drain()
                result = await self.commands.get()

                reply = result.get("Reply-Text", "")
                if reply.startswith("-ERR"):
                    try:
                        command_errors_counter.add(
                            1,
                            attributes={
                                "command": command_name,
                                "error": "protocol_error",
                            },
                        )
                    except Exception:
                        pass

                return result
            except Exception as e:
                try:
                    command_errors_counter.add(
                        1,
                        attributes={"command": command_name, "error": type(e).__name__},
                    )
                except Exception:
                    pass
                raise
            finally:
                try:
                    duration = time.perf_counter() - start_time
                    command_duration_histogram.record(
                        duration, attributes={"command": command_name}
                    )
                except Exception:
                    pass
