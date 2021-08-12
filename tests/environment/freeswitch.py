"""
Freeswitch module
-----------------

Aggregate created to provide the necessary material to simulate a freeswitrch server in test environments.


    Example:

    async with Freeswitch("0.0.0.0", 8021, "Cluecon"):
        ...

Remembering that we only simulate the communication via ESL and not the processing of SIP calls.
"""
from __future__ import annotations

from asyncio import (
    ensure_future,
    StreamReader,
    StreamWriter,
    start_server,
    sleep,
)
from typing import List, Awaitable, Callable, Optional, Union
from asyncio.base_events import Server
from functools import partial
from copy import copy
import socket

from environment import COMMANDS, EVENTS


class Freeswitch:
    """
    Freeswitch class
    ------------

    Given a valid address, simulate a freeswitch server for testing using ESL.

    Attributes:
    - host: required
        IPv4 address where we will receive ESL connections.
    - port: required
        Port where we will receive ESL connections.
    - password: required
        Password used to authenticate a new connection.
    """

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        events: Optional[List[str]] = None,
    ) -> None:
        self.processor: Optional[Awaitable] = None
        self.queue = events if events else list()
        self.server: Optional[Server] = None
        self.password = password
        self.commands = COMMANDS
        self.is_running = False
        self.events = EVENTS
        self.host = host
        self.port = port

    async def stop(self) -> Awaitable[None]:
        """Stop current server."""
        if self.server:
            self.is_running = False
            self.server.close()
            await self.server.wait_closed()

            if self.processor:
                self.processor.cancel()

            await sleep(0.00001)

    async def start(self) -> Awaitable[None]:
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        self.processor = ensure_future(self.server.serve_forever())
        self.is_running = True

    async def __aenter__(self) -> Awaitable[Server]:
        """Interface used to implement a context manager."""
        await self.start()
        return await self.server.__aenter__()

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        await self.stop()

    @staticmethod
    async def send(
        writer: StreamWriter, lines: Union[List[str], str]
    ) -> Awaitable[None]:
        """Given a line-separated message, we send the ESL client."""
        if isinstance(lines, str):
            writer.write((lines + "\n").encode("utf-8"))

        else:
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

        writer.write("\n".encode("utf-8"))
        await writer.drain()

    async def shoot(self, writer: StreamWriter) -> None:
        if self.queue:
            for event in self.queue:
                await self.send(writer, event.splitlines())

    async def event(self, writer: StreamWriter, event: str) -> Awaitable[None]:
        content = self.events.get(event)
        length = len(content)
        await self.send(
            writer, ["Content-Type: text/event-plain", f"Content-Length: {length}"]
        )
        await self.send(writer, [content.strip()])

    async def command(self, writer: StreamWriter, command: str) -> Awaitable[None]:
        """Response an ESL command received."""
        await self.send(
            writer, ["Content-Type: command/reply", f"Reply-Text: {command}"]
        )

    async def api(self, writer: StreamWriter, content: str) -> Awaitable[None]:
        """Response an API statement received via ESL."""
        length = len(content)
        await self.send(
            writer,
            [
                "Content-Type: api/response",
                f"Content-Length: {length}",
                *content.strip().splitlines(),
            ],
        )

    async def disconnect(self, writer: StreamWriter) -> Awaitable[None]:
        """Appropriately closes an ESL connection."""
        await self.send(
            writer, ["Content-Type: text/disconnect-notice", "Content-Length: 67"]
        )
        await self.send(
            writer,
            [
                "Disconnected, goodbye.",
                "See you at ClueCon! http://www.cluecon.com/",
            ],
        )
        if not writer.is_closing():
            writer.close()
            await writer.wait_closed()

    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        """Given an ESL event, we process it."""
        payload = copy(request)

        if payload.startswith("auth"):
            received_password = payload.split().pop().strip()

            if self.password == received_password:
                await self.command(writer, "+OK accepted")
                await self.shoot(writer)

            else:
                await self.command(writer, "-ERR invalid")
                await self.disconnect(writer)

        elif payload == "exit":
            await self.command(writer, "+OK bye")
            await self.disconnect(writer)
            await self.stop()

        elif payload in self.commands:
            response = self.commands.get(payload)

            if payload.startswith("api"):
                await self.api(writer, response)

            else:
                await self.command(writer, response)

        elif payload.startswith("api"):
            command = payload.replace("api", "").split().pop().strip()
            await self.command(writer, f"-ERR {command} command not found")

        else:
            await self.command(writer, "-ERR command not found")

    @staticmethod
    async def handler(
        server: Freeswitch, reader: StreamReader, writer: StreamWriter
    ) -> Awaitable[None]:
        """Handle new ESL-based connections."""
        await server.send(writer, ["Content-Type: auth/request"])

        while server.is_running:
            request = None
            buffer = ""

            while server.is_running and not writer.is_closing():
                try:
                    content = await reader.read(1)

                except:
                    server.is_running = False
                    await server.stop()
                    break

                buffer += content.decode("utf-8")

                if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                    request = buffer
                    break

            request = buffer.strip()

            if not request or not server.is_running:
                break

            else:
                await server.process(writer, request)
