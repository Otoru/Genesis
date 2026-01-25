"""
Genesis Protocol
----------------

Here we will group what is common to the ESL client for inbound and outbound connections.
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

from opentelemetry import trace, metrics
from rich.console import Console

from genesis.exceptions import ConnectionError, UnconnectedError
from genesis.logger import logger, TRACE_LEVEL_NUM
from genesis.parser import ESLEvent, parse_headers

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

commands_sent_counter = meter.create_counter(
    "genesis.commands.sent",
    description="Number of ESL commands sent",
    unit="1",
)
events_received_counter = meter.create_counter(
    "genesis.events.received",
    description="Number of ESL events received",
    unit="1",
)
command_duration_histogram = meter.create_histogram(
    "genesis.commands.duration",
    description="Duration of ESL commands execution",
    unit="s",
)
command_errors_counter = meter.create_counter(
    "genesis.commands.errors",
    description="Number of failed ESL commands",
    unit="1",
)

# Channel operation metrics
channel_operations_counter = meter.create_counter(
    "genesis.channel.operations",
    description="Number of channel operations",
    unit="1",
)

channel_operation_duration = meter.create_histogram(
    "genesis.channel.operation.duration",
    description="Duration of channel operations",
    unit="s",
)

hangup_causes_counter = meter.create_counter(
    "genesis.channel.hangup.causes",
    description="Hangup causes",
    unit="1",
)

bridge_operations_counter = meter.create_counter(
    "genesis.channel.bridge.operations",
    description="Bridge operations",
    unit="1",
)

dtmf_received_counter = meter.create_counter(
    "genesis.channel.dtmf.received",
    description="DTMF digits received",
    unit="1",
)

call_duration_histogram = meter.create_histogram(
    "genesis.call.duration",
    description="Total call duration from creation to hangup",
    unit="s",
)

timeout_counter = meter.create_counter(
    "genesis.timeouts",
    description="Number of timeouts",
    unit="1",
)


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
        self.handlers: Dict[
            str,
            List[
                Union[
                    Callable[[ESLEvent], None],
                    Callable[[ESLEvent], Coroutine[Any, Any, None]],
                ]
            ],
        ] = {}

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
                # OTel Tracing
                attributes = {}
                for key, value in event.items():
                    if key == "Event-Name":
                        attr_name = "event.name"
                    elif key == "Unique-ID":
                        attr_name = "event.uuid"
                    elif key == "Content-Type":
                        attr_name = "event.content_type"
                    else:
                        slug = key.lower().replace("-", "_")
                        attr_name = f"event.header.{slug}"

                    if isinstance(value, (str, int, float, bool, list, tuple)):
                        attributes[attr_name] = value

                try:
                    with tracer.start_as_current_span(
                        "process_event", attributes=attributes
                    ) as span:
                        for header_name, header_value in event.items():
                            # Encode headers if necessary or ensure string
                            attribute_key = header_name.lower().replace("-", "_")
                            span.set_attribute(
                                f"event.header.{attribute_key}", str(header_value)
                            )

                        event_name = event.get("Event-Name", "UNKNOWN")
                        content_type = event.get("Content-Type", "UNKNOWN")
                        metric_attributes = {
                            "event_name": event_name,
                            "content_type": content_type,
                        }

                        if "Event-Subclass" in event:
                            metric_attributes["event_subclass"] = event[
                                "Event-Subclass"
                            ]
                        if "Call-Direction" in event:
                            metric_attributes["direction"] = event["Call-Direction"]
                        if "Channel-State" in event:
                            metric_attributes["channel_state"] = event["Channel-State"]
                        if "Answer-State" in event:
                            metric_attributes["answer_state"] = event["Answer-State"]
                        if "Hangup-Cause" in event:
                            metric_attributes["hangup_cause"] = event["Hangup-Cause"]
                except Exception:
                    # OTel not initialized or error in tracing - continue without tracing
                    event_name = event.get("Event-Name", "UNKNOWN")
                    content_type = event.get("Content-Type", "UNKNOWN")
                    metric_attributes = {
                        "event_name": event_name,
                        "content_type": content_type,
                    }

                try:
                    events_received_counter.add(1, attributes=metric_attributes)
                except Exception:
                    pass

                # LOGGING
                try:
                    if logger.isEnabledFor(TRACE_LEVEL_NUM):
                        logger.trace(f"Received an event: '{event}'.")

                    else:
                        if logger.isEnabledFor(logging.DEBUG):
                            name = event.get("Event-Name", None)
                            uuid = event.get("Unique-ID", None)

                            if uuid:
                                logger.debug(
                                    f"Received an event: '{name}' for call '{uuid}'. "
                                )

                                if name == "CHANNEL_EXECUTE_COMPLETE":
                                    application = event.get("Application")
                                    response = event.get("Application-Response")

                                    logger.debug(
                                        f"Application: '{application}' - Response: '{response}'."
                                    )

                            else:
                                if name:
                                    logger.debug(f"Received an event: '{name}'.")

                                elif "Content-Type" in event and event[
                                    "Content-Type"
                                ] in [
                                    "command/reply",
                                    "auth/request",
                                ]:
                                    reply = event.get("Reply-Text", None)

                                    if (
                                        reply
                                        and event["Content-Type"] == "command/reply"
                                    ):
                                        logger.debug(
                                            f"Received an command reply: '{reply}'."
                                        )

                                    if (
                                        reply
                                        and event["Content-Type"] == "auth/request"
                                    ):
                                        logger.debug(
                                            f"Received an authentication reply: '{event}'."
                                        )

                except Exception as e:
                    logger.error(f"Error logging event: {str(e)} - Event: {event}")

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

                identifier = event.get("Event-Name", None)

                if identifier == "CUSTOM":
                    name = event.get("Event-Subclass", None)
                else:
                    name = identifier

                if name:
                    logger.trace(f"Get all handlers for '{name}'.")
                    specific = self.handlers.get(name, [])
                    generic = self.handlers.get("*", list())
                    handlers = specific + generic

                    if handlers:
                        for handler in handlers:
                            if iscoroutinefunction(handler):
                                create_task(handler(event))
                            else:
                                create_task(to_thread(handler, event))

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
