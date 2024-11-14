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
    Event,
    Queue,
    Task,
    to_thread,
)
from typing import List, Awaitable, Dict, NoReturn, Optional, Callable, Coroutine, Any, Union
from inspect import isawaitable
from abc import ABC

from genesis.exceptions import UnconnectedError, ConnectionError
from genesis.parser import parse_headers, ESLEvent
from genesis.logger import logger


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
        self.handlers: Dict[str, List[Union[
            Callable[[ESLEvent], None],
            Callable[[ESLEvent], Coroutine[Any, Any, None]]
        ]]] = {}

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

                except:
                    self.is_connected = False
                    break

                if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                    request = buffer
                    logger.debug(f"<<< Complete message received: {repr(request)}")
                    break

            if not request or not self.is_connected:
                break

            event = parse_headers(request)

            if "Content-Length" in event:
                length = int(event["Content-Length"])
                logger.debug(f"Read more {length} bytes.")
                data = await self.reader.readexactly(length)
                logger.debug(f"Received data: {data}")
                result = data.decode("utf-8")

                if "Content-Type" in event:
                    content = event["Content-Type"]
                    logger.debug(f"Check content type of event: {event}")

                    if content not in ["api/response", "text/rude-rejection", "log/data"]:
                        headers = parse_headers(result)
                        logger.debug(f"Received headers: {headers}")

                        if "Content-Length" in headers:
                            length = int(headers["Content-Length"])
                            logger.debug(f"Read more {length} bytes.")
                            data = await self.reader.readexactly(length)
                            result = data.decode("utf-8")

                            logger.debug(f"Received body: {result}")
                            event.body = result

                        event.update(headers)
                    else:
                        event.body = result

                else:
                    event.body = result

            await self.events.put(event)

    async def consume(self) -> None:
        """Arm all event processors."""
        while self.is_connected:
            event = await self.events.get()
            logger.debug(f"Received an event: '{event}'.")

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
                logger.debug(f"Get all handlers for '{name}'.")
                specific = self.handlers.get(name, [])
                generic = self.handlers.get("*", list())
                handlers = specific + generic

                if handlers:
                    for handler in handlers:
                        if iscoroutinefunction(handler):
                            create_task(handler(event))
                        else:
                            create_task(to_thread(handler, event))

    def on(self, key: str, handler: Union[
           Callable[[ESLEvent], None],
           Callable[[ESLEvent], Coroutine[Any, Any, None]]
       ]) -> None:
        """Associate a handler with an event key."""
        logger.debug(f"Register handler to '{key}' event.")
        self.handlers.setdefault(key, list()).append(handler)

    def remove(self, key: str, handler: Union[
           Callable[[ESLEvent], None],
           Callable[[ESLEvent], Coroutine[Any, Any, None]]
       ]) -> None:
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
