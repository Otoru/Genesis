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
)
from typing import List, Dict, Optional, Callable, Coroutine, Any, Union
from abc import ABC
import logging

from genesis.exceptions import UnconnectedError, ConnectionError
from genesis.parser import parse_headers, ESLEvent
from genesis.logger import logger, TRACE_LEVEL_NUM


class Protocol(ABC):
    def __init__(self):
        self.events = Queue()
        self.commands = Queue()
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

        if self.consumer and not self.consumer.cancelled():
            logger.debug("Cancel event consumer task.")
            self.consumer.cancel()

    async def handler(self) -> None:
        """Defines intelligence to treat received events."""
        while self.is_connected:
            request = None
            buffer = ""

            while self.is_connected:
                try:
                    content = await self.reader.readline()
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
                logger.trace(f"Received complete data: {data}")
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
                            # If no clear header/body separation, treat everything as body
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

                            elif "Content-Type" in event and event["Content-Type"] in [
                                "command/reply",
                                "auth/request",
                            ]:
                                reply = event.get("Reply-Text", None)

                                if reply and event["Content-Type"] == "command/reply":
                                    logger.debug(
                                        f"Received an command reply: '{reply}'."
                                    )

                                if reply and event["Content-Type"] == "auth/request":
                                    logger.debug(
                                        f"Received an authentication reply: '{event}'."
                                    )

            except Exception as e:
                logger.error(f"Error logging event: {str(e)} - Event: {event}")

            if "Content-Type" in event and event["Content-Type"] == "auth/request":
                self.authentication_event.set()

            elif "Content-Type" in event and event["Content-Type"] == "command/reply":
                await self.commands.put(event)

            elif "Content-Type" in event and event["Content-Type"] == "api/response":
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

    def on(
        self,
        key: str,
        handler: Union[
            Callable[[ESLEvent], None], Callable[[ESLEvent], Coroutine[Any, Any, None]]
        ],
    ) -> None:
        """Associate a handler with an event key."""
        logger.debug(f"Register handler to '{key}' event.")
        self.handlers.setdefault(key, list()).append(handler)

    def remove(
        self,
        key: str,
        handler: Union[
            Callable[[ESLEvent], None], Callable[[ESLEvent], Coroutine[Any, Any, None]]
        ],
    ) -> None:
        """Removes the HANDLER from the list of handlers for the given event KEY name."""
        logger.debug(f"Remove handler to '{key}' event.")
        if key in self.handlers and handler in self.handlers[key]:
            self.handlers.setdefault(key, list()).remove(handler)

    async def send(self, cmd: str) -> ESLEvent:
        """Method used to send commands to or freeswitch."""
        if not self.is_connected:
            raise UnconnectedError()

        if self.writer.is_closing():
            raise ConnectionError()

        logger.debug(f"Send command to freeswitch: '{cmd}'.")
        lines = cmd.splitlines()

        for line in lines:
            self.writer.write((line + "\n").encode("utf-8"))

        self.writer.write("\n".encode("utf-8"))
        await self.writer.drain()

        response = await self.commands.get()
        return response
