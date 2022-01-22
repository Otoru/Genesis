"""
Genesis Protocol
----------------

Here we will group what is common to the ESL client for inbound and outbound connections.
"""
from asyncio import StreamWriter, StreamReader, Queue, create_task, Task, Event
from typing import List, Awaitable, Dict, NoReturn, Optional, Union
from inspect import isawaitable, iscoroutinefunction
from pprint import pformat
from abc import ABC
import logging

from genesis.exceptions import UnconnectedError, ConnectionError
from genesis.parser import parse


class Protocol(ABC):
    def __init__(self):
        self.cmd = Queue()
        self.events = Queue()
        self.is_connected = False
        self.is_lingering = False
        self.authentication_event = Event()
        self.producer: Optional[Task] = None
        self.consumer: Optional[Task] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.handlers: Dict[str, List[Awaitable[None]]] = {}

    async def start(self) -> Awaitable[None]:
        self.is_connected = True

        logging.debug("Create tasks to work with ESL events.")
        self.producer = create_task(self.handler())
        self.consumer = create_task(self.consume())

    async def stop(self) -> Awaitable[None]:
        if self.writer and not self.writer.is_closing():
            logging.debug("Closer stream writter.")
            self.writer.close()

        self.is_connected = False

        if self.producer and not self.producer.cancelled():
            logging.debug("Cancel event producer task.")
            self.producer.cancel()

        if self.consumer and not self.consumer.cancelled():
            logging.debug("Cancel event consumer task.")
            self.consumer.cancel()

    async def handler(self) -> Awaitable[NoReturn]:
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
                    break

            if not request or not self.is_connected:
                break

            event = parse(request)
            await self.events.put(event)

    async def consume(self) -> Awaitable[NoReturn]:
        while self.is_connected:
            event = await self.events.get()
            formated_event = pformat(event)
            logging.debug(f"Recived an event: '{formated_event}'.")

            if "Content-Type" in event and event["Content-Type"] == "auth/request":
                self.authentication_event.set()

            elif "Content-Type" in event and event["Content-Type"] == "command/reply":
                await self.cmd.put(event)

            elif "Content-Type" in event and event["Content-Type"] == "api/response":
                await self.cmd.put(event)

            elif "Content-Type" in event and event["Content-Type"] in [
                "text/rude-rejection",
                "text/disconnect-notice",
            ]:
                if (
                    "Content-Disposition" in event
                    and event["Content-Disposition"] == "linger"
                ):
                    logging.debug("Set linger condition")
                    self.is_lingering = True
                else:
                    await self.stop()

            identifier = event.get("Event-Name", None)

            if identifier == "CUSTOM":
                name = event.get("Event-Subclass", None)
            else:
                name = identifier

            if name:
                logging.debug(f"Get all handler for '{name}'.")
                specific = self.handlers.get(name, list())
                generic = self.handlers.get("*", list())
                handlers = specific + generic

                if handlers:
                    for handler in handlers:
                        if isawaitable(handler) or iscoroutinefunction(handler):
                            await handler(event)

                        else:
                            logging.error("Invalid handler")
                            raise TypeError("Invalid handler")

    def on(self, key: str, handler: Awaitable[None]) -> None:
        """Associate a handler with an event key."""
        self.handlers.setdefault(key, list()).append(handler)

    def remove(self, key: str, handler: Awaitable[None]) -> None:
        """Removes the HANDLER from the list of handlers for the given event KEY name."""
        if key in self.handlers and handler in self.handlers[key]:
            self.handlers.setdefault(key, list()).remove(handler)

    async def send(self, cmd: str) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        if not self.is_connected:
            raise UnconnectedError()

        if self.writer.is_closing():
            raise ConnectionError()

        logging.debug(f"Send command to freeswitch: '{cmd}'.")
        lines = cmd.splitlines()

        for line in lines:
            self.writer.write((line + "\n").encode("utf-8"))

        self.writer.write("\n".encode("utf-8"))
        await self.writer.drain()

        response = await self.cmd.get()
        return response
