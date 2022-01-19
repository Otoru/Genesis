"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""
from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, start_server
from typing import Awaitable, NoReturn, Dict
from functools import partial
import socket

from genesis.exceptions import UnconnectedError
from genesis.protocol import BaseProtocol


class Session(BaseProtocol):
    """
    Session class
    -------------

    Abstracts a session established between the application and the freeswitch.
    """

    def __init__(self, reader: StreamReader, writer: StreamWriter) -> None:
        self.context = dict()
        self.reader = reader
        self.writer = writer
        self.is_connected = False
        self.commands = Queue()

    async def send(self, command: str) -> Awaitable[Dict[str, str]]:
        """Method used to send commands to or freeswitch."""

        if not self.is_connected:
            raise UnconnectedError()

        content = command.splitlines()

        await super().send(self.writer, content)
        response = await self.commands.get()
        return response

    async def answer(self) -> Awaitable[None]:
        ...

    async def hangup(self) -> Awaitable[None]:
        ...

    async def playback(self, path: str, block: bool = True) -> Awaitable[None]:
        ...


class Outbound:
    """
    Outbound class
    -------------

    Given a valid set of information, start an ESL server that processes calls.

    Attributes:
    - host: required
        IP address the server should listen on.
    - port: required
        Network port the server should listen on.
    - handler: required
        Function that will take a session as an argument and will actually process the call.
    - size: optional
        Maximum number of simultaneous sessions the server will support.
    - events: optional
        If true, ask freeswitch to send us all events associated with the session.
    - linger: optional
        If true, asks that the events associated with the session come even after the call hangup.
    """

    def __init__(
        self,
        host: str,
        port: int,
        handler: Awaitable,
        size: int = 100,
        events: bool = True,
        linger: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.app = handler
        self.size = size
        self.myevents = events
        self.linger = linger
        self.server = None

    async def start(self) -> Awaitable[NoReturn]:
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        async with self.server:
            await self.server.serve_forever()

    async def stop(self) -> Awaitable[None]:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> Awaitable[None]:
        session = Session(reader, writer)
        session.context = await session.send("connect")

        if server.myevents:
            reply = await session.send("myevents")

        if server.linger:
            reply = await session.send("linger")

        await server.app(session)
