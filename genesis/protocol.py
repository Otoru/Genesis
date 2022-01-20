"""
Genesis Protocol
----------------

Here we will group what is common to the ESL client for inbound and outbound connections.
"""
from typing import List, Awaitable, Dict, NoReturn, Optional, Union
from asyncio import StreamWriter, StreamReader, Queue, create_task
from inspect import isawaitable, iscoroutinefunction
from abc import ABC
import logging

from genesis.parser import parse

class BaseProtocol(ABC):
    """
    BaseProtocol Class
    ------------------

    Contains methods common to inbound and outbound connectors.
    """

    def __init__(self) -> None:
        self.handlers: Dict[str, List[Awaitable[None]]] = {}
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.is_connected = False
        self.events = Queue()

    async def consume(
        self, event: Dict[str, Union[str, List[str]]]
    ) -> Awaitable[NoReturn]:
        """Arm all event processors."""
        identifier = event.get("Event-Name", None)

        if identifier == "CUSTOM":
            name = event.get("Event-Subclass", None)
        else:
            name = identifier

        if name:
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
        try:
            self.handlers.setdefault(key, list()).remove(handler)
        except ValueError:
            message = "'{0!s}' is not a valid handler of '{1!s}'".format(handler, key)
            logging.error(message)
            raise ValueError(message)

    async def handler(self) -> Awaitable[NoReturn]:
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
                    break

            if not request or not self.is_connected:
                break

            event = parse(request)
            await self.events.put(event)

    @staticmethod
    async def send(writer: StreamWriter, lines: List[str]) -> Awaitable[None]:
        """Method used to send commands to or freeswitch."""
        if not writer.is_closing():
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

            writer.write("\n".encode("utf-8"))
            await writer.drain()

    async def disconnect(self) -> Awaitable[None]:
        if self.writer and not self.writer.is_closing():
            self.writer.close()

        self.is_connected = False
