"""
Genesis inbound
---------------

ESL implementation used for incoming connections on freeswitch.
"""
from __future__ import annotations

from asyncio import (
    open_connection,
    TimeoutError,
    create_task,
    wait_for,
    Queue,
    Event,
)
from typing import Awaitable, Optional, List, Dict, NoReturn
import logging

from genesis.exceptions import (
    ConnectionTimeoutError,
    AuthenticationError,
    UnconnectedError,
)
from genesis.protocol import BaseProtocol
from genesis.parser import parse


class Client(BaseProtocol):
    """
    Client class
    -------------

    Given a valid set of information, establish a connection to a freeswitch server.

    Attributes:
    - host: required
        IP address associated with the connection destination server.
    - port: required
        Network port where ESL module is listening.
    - password: required
        Password used for authentication on freeswitch.
    - timeout: optional
        Maximum time we wait to initiate a connection.
    """

    def __init__(self, host: str, port: int, password: str, timeout: int = 5) -> None:
        super().__init__()
        self.producer: Optional[Awaitable] = None
        self.consumer: Optional[Awaitable] = None
        self.password = password
        self.commands = Queue()
        self.trigger = Event()
        self.timeout = timeout
        self.host = host
        self.port = port

    async def __aenter__(self) -> Awaitable[Client]:
        """Interface used to implement a context manager."""
        await self.connect()
        return self

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        await self.disconnect()

    async def send(self, command: str) -> Awaitable[Dict[str, str]]:
        """Method used to send commands to or freeswitch."""

        if not self.is_connected:
            raise UnconnectedError()

        content = command.splitlines()
        logging.debug(f"Send command: {content}")

        await super().send(self.writer, content)
        response = await self.commands.get()
        return response

    async def authenticate(self) -> Awaitable[None]:
        """Authenticates to the freeswitch server. Raises an exception on failure."""
        await self.trigger.wait()
        response = await self.send(f"auth {self.password}")

        if response["Reply-Text"] != "+OK accepted":
            raise AuthenticationError("Invalid password")

    async def consume(self) -> Awaitable[NoReturn]:
        """Arm all event producers."""
        self.is_connected = True
        self.producer = create_task(self.handler())

        while self.is_connected:
            event = await self.events.get()
            logging.debug(f"Event received: {event}")

            if "Content-Type" in event and event["Content-Type"] == "auth/request":
                self.trigger.set()

            elif "Content-Type" in event and event["Content-Type"] == "command/reply":
                await self.commands.put(event)

            elif "Content-Type" in event and event["Content-Type"] == "api/response":
                await self.commands.put(event)

            elif "Content-Type" in event and (
                event["Content-Type"] == "text/disconnect-notice"
                or event["Content-Type"] == "text/rude-rejection"
            ):
                await self.disconnect()

            await super().consume(event)

    async def connect(self) -> Awaitable[None]:
        """Initiates an authenticated connection to a freeswitch server."""
        try:
            promise = open_connection(self.host, self.port)
            self.reader, self.writer = await wait_for(promise, self.timeout)
        except TimeoutError:
            raise ConnectionTimeoutError()

        self.consumer = create_task(self.consume())
        await self.authenticate()

    async def disconnect(self) -> Awaitable[None]:
        """Terminates connection to a freeswitch server."""
        if self.writer and not self.writer.is_closing():
            self.writer.close()

        self.is_connected = False

        if self.producer:
            self.producer.cancel()

        if self.consumer:
            self.consumer.cancel()
