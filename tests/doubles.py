from __future__ import annotations

from uuid import uuid4
import socket
import string
import asyncio
from abc import ABC, abstractmethod
from asyncio import (
    Future,
    StreamReader,
    StreamWriter,
    ensure_future,
    open_connection,
    start_server,
)
from asyncio.base_events import Server
from contextlib import closing
from copy import copy
from functools import partial
from random import choices
from typing import Awaitable, Callable, Dict, List, Optional, Union

from genesis.parser import parse_headers


def get_free_tcp_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def get_random_password(length: int) -> str:
    options = string.ascii_letters + string.digits + string.punctuation
    result = "".join(choices(options, k=length))
    return result


class ESLMixin(ABC):
    is_running: bool
    commands: Dict[str, Union[str, Callable[[], str]]]

    def __init__(self):
        self.writers: set[StreamWriter] = set()
        self.tasks: set[asyncio.Task] = set()

    @staticmethod
    async def send(writer: StreamWriter, lines: Union[List[str], str]) -> None:
        if isinstance(lines, str):
            writer.write((lines + "\n").encode("utf-8"))

        else:
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

        writer.write("\n".encode("utf-8"))
        await writer.drain()

    def oncommand(self, command: str, response: Union[str, Callable[[], str]]) -> None:
        self.commands[command] = response

    @abstractmethod
    async def process(self, writer: StreamWriter, request: str) -> None:
        raise NotImplementedError()

    @staticmethod
    async def handler(
        server: ESLMixin, reader: StreamReader, writer: StreamWriter, dial: bool
    ) -> None:
        task = asyncio.current_task()
        if hasattr(server, "tasks") and task:
            server.tasks.add(task)

        if hasattr(server, "writers"):
            server.writers.add(writer)

        try:
            if not dial:
                # Send initialauth request
                await server.send(writer, ["Content-Type: auth/request"])

            while server.is_running:
                try:
                    # Improved reading using readuntil
                    data = await reader.readuntil(b"\n\n")
                    request = data.decode("utf-8").strip()
                except Exception:
                    # Connection closed or error
                    if hasattr(server, "stop") and callable(server.stop):
                        await server.stop()
                    break

                if not request:
                    break

                # Process the request
                await server.process(writer, request)
        finally:
            if server.is_running and not writer.is_closing():
                writer.close()
                await writer.wait_closed()

            if hasattr(server, "writers"):
                server.writers.discard(writer)

            if hasattr(server, "tasks") and task:
                server.tasks.discard(task)


class Freeswitch(ESLMixin):
    def __init__(self, host: str, port: int, password: str) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.is_running = False
        self.commands = dict()
        self.events: List[str] = list()
        self.received_commands: List[str] = list()
        self.filters: List[tuple[str, str]] = list()
        self.calls: Dict[str, str] = dict()
        self.hangups: List[tuple[str, str]] = list()
        self.bridges: List[tuple[str, str]] = list()
        self.server: Optional[Server] = None
        self.processor: Optional[Future] = None
        self._stop_lock = asyncio.Lock()

    @property
    def address(self) -> tuple[str, int, str]:
        return (self.host, self.port, self.password)

    async def shoot(self, writer: StreamWriter) -> None:
        if self.events:
            for event in self.events:
                await self.send(writer, event.splitlines())

    async def broadcast(self, event_headers: str) -> None:
        """Sends an event to all connected writers."""
        for writer in self.writers:
            if not writer.is_closing():
                await self.send(writer, event_headers.splitlines())

    async def start(self) -> None:
        # Properly type the partial for start_server
        # The handler expected by start_server is (reader, writer) -> None/Awaitable
        # Our handler is staticmethod (server, reader, writer, dial) -> None

        self.client_connected = asyncio.Event()

        async def _client_connected_cb(
            reader: StreamReader, writer: StreamWriter
        ) -> None:
            self.client_connected.set()
            await self.handler(self, reader, writer, dial=False)

        self.port = 0
        self.server = await start_server(
            _client_connected_cb,
            self.host,
            self.port,
            family=socket.AF_INET,
            reuse_address=True,
        )
        self.port = self.server.sockets[0].getsockname()[1]
        self.is_running = True

    async def stop(self) -> None:
        async with self._stop_lock:
            if not self.is_running:
                return
            self.is_running = False

            # 1. Close the server (stops accepting new connections)
            if self.server:
                self.server.close()

            # 2. Cancel all handler tasks (close active connections)
            current_task = asyncio.current_task()
            for task in list(self.tasks):
                if task is not current_task and not task.done():
                    task.cancel()
                    try:
                        await task
                    except (Exception, asyncio.CancelledError):
                        pass

            # 3. Wait for server to fully close
            if self.server:
                pass

            # 4. Close all connection writers
            for writer in list(self.writers):
                if not writer.is_closing():
                    writer.close()
                try:
                    await writer.wait_closed()
                except (Exception, asyncio.CancelledError):
                    pass

    async def __aenter__(self) -> Freeswitch:
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        await self.stop()

    async def command(self, writer: StreamWriter, command: str) -> None:
        await self.send(
            writer, ["Content-Type: command/reply", f"Reply-Text: {command}"]
        )

    async def api(self, writer: StreamWriter, content: str) -> None:
        length = len(content)
        await self.send(
            writer,
            [
                "Content-Type: api/response",
                f"Content-Length: {length}",
                "",
                *content.strip().splitlines(),
            ],
        )

    async def disconnect(self, writer: StreamWriter) -> None:
        await self.send(
            writer,
            [
                "Content-Type: text/disconnect-notice",
                "Content-Length: 67",
            ],
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

    async def process(self, writer: StreamWriter, request: str) -> None:
        # Use genesis parser to parse the request headers
        parsed = parse_headers(request)
        payload = copy(request)

        # Store received command for verification
        self.received_commands.append(payload)

        if payload.startswith("sendmsg"):
            # Mock behavior for blocking commands
            # We need to parse the headers manually from the payload for the mock
            # payload is: "sendmsg <uuid>\nKey: Value..."
            lines = payload.splitlines()
            headers = {}
            for line in lines[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key] = value

            await self.command(writer, "+OK")

            # If it's an execute command with Event-UUID, send the complete event
            if headers.get("call-command") == "execute" and "Event-UUID" in headers:
                event_uuid = headers["Event-UUID"]
                # Simulate async completion
                await asyncio.sleep(0.01)

                body_lines = [
                    "Event-Name: CHANNEL_EXECUTE_COMPLETE",
                    f"Application-UUID: {event_uuid}",
                    "Unique-ID: test-unique-id",
                ]
                body = "\n".join(body_lines)
                length = len(body)

                await self.send(
                    writer,
                    [
                        "Content-Type: text/event-plain",
                        f"Content-Length: {length}",
                        "",
                        body,
                    ],
                )

        elif payload.startswith("auth"):
            received_password = payload.split().pop().strip()

            if self.password == received_password:
                await self.command(writer, "+OK accepted")

            else:
                await self.command(writer, "-ERR invalid")
                await self.disconnect(writer)

        elif payload == "exit":
            await self.command(writer, "+OK bye")
            await self.disconnect(writer)
            await self.stop()

        elif payload == "events plain ALL":
            await self.command(writer, "+OK event listener enabled plain")
            await self.shoot(writer)

        elif payload.startswith("api create_uuid"):
            uuid = str(uuid4())
            await self.api(writer, uuid)

        elif payload.startswith("filter"):
            parts = payload.split()
            if len(parts) >= 3:
                header = parts[1]
                value = parts[2]
                self.filters.append((header, value))
            await self.command(writer, f"+OK filter added. [{header}]=[{value}]")

        elif payload.startswith("api uuid_kill"):
            # payload example: api uuid_kill <uuid> <cause>
            parts = payload.split()
            if len(parts) >= 4:
                uuid = parts[2]
                cause = parts[3]
                self.hangups.append((uuid, cause))
            elif len(parts) >= 3:
                uuid = parts[2]
                cause = "NORMAL_CLEARING"  # Default if not specified, though Channel sends it.
                self.hangups.append((uuid, cause))

            await self.api(writer, "+OK")

        elif payload.startswith("api uuid_bridge"):
            # payload example: api uuid_bridge <uuid> <other_uuid>
            parts = payload.split()
            if len(parts) >= 4:
                uuid = parts[2]
                other_uuid = parts[3]
                self.bridges.append((uuid, other_uuid))
            await self.api(writer, f"+OK {other_uuid}")

        elif payload.startswith("api originate"):
            import re

            match = re.search(r"origination_uuid=([a-fA-F0-9-]+)", payload)
            if match:
                uuid = match.group(1)
                # Store the dial path as the value
                # payload example: api originate {origination_uuid=...}user/1000 &park()
                dial_path = payload.split("}")[-1].replace(" &park()", "").strip()
                self.calls[uuid] = dial_path
                await self.api(writer, f"+OK {uuid}")
            else:
                # Generate one if not provided (though Channel always provides it)
                uuid = str(uuid4())
                await self.api(writer, f"+OK {uuid}")

        elif payload in self.commands:
            response = self.commands.get(payload)
            if callable(response):
                response = response()

            if payload.startswith("api"):
                # Ensure response is str
                if not isinstance(response, str):
                    response = str(response)
                await self.api(writer, response)

            else:
                if not isinstance(response, str):
                    response = str(response)
                await self.command(writer, response)

        else:
            if payload.startswith("api"):
                command = payload.replace("api", "").split().pop().strip()
                await self.command(writer, f"-ERR {command} command not found")

            else:
                await self.command(writer, "-ERR command not found")


class Dialplan(ESLMixin):
    def __init__(self) -> None:
        super().__init__()
        self.commands = dict()
        self.is_running = False
        self.worker: Optional[Future] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

    async def broadcast(self, event_headers: Dict[str, str]) -> None:
        """Send a generic event."""
        # Use the same format as CHANNEL_EXECUTE_COMPLETE in process method
        body_lines = [f"{key}: {value}" for key, value in event_headers.items()]
        # Content-Length should be the size of the body content
        # Each line gets a \n, but we don't count the final \n added by send()
        body_text = "\n".join(body_lines)
        length = len(body_text)

        # Use self.writer (same as used in process method for CHANNEL_EXECUTE_COMPLETE)
        if self.writer and not self.writer.is_closing():
            await self.send(
                self.writer,
                [
                    "Content-Type: text/event-plain",
                    f"Content-Length: {length}",
                    "",
                    *body_lines,  # Unpack the list so each line is sent separately
                ],
            )

    async def process(self, writer: StreamWriter, request: str) -> None:
        payload = copy(request)

        # Handle sendmsg commands (for blocking command tests)
        if payload.startswith("sendmsg"):
            # Parse headers from sendmsg payload
            lines = payload.splitlines()
            headers = {}
            for line in lines[1:]:
                if ": " in line:
                    key, value = line.split(": ", 1)
                    headers[key] = value

            # Send +OK reply
            await self.send(writer, ["Content-Type: command/reply", "Reply-Text: +OK"])

            # If it's an execute command with Event-UUID, send CHANNEL_EXECUTE_COMPLETE
            if headers.get("call-command") == "execute" and "Event-UUID" in headers:
                event_uuid = headers["Event-UUID"]
                # Simulate async completion
                await asyncio.sleep(0.01)

                body_lines = [
                    "Event-Name: CHANNEL_EXECUTE_COMPLETE",
                    f"Application-UUID: {event_uuid}",
                    "Unique-ID: test-unique-id",
                ]
                # Content-Length should be the size of the body content
                # Each line gets a \n, but we don't count the final \n added by send()
                body_text = "\n".join(body_lines)
                length = len(body_text)

                await self.send(
                    writer,
                    [
                        "Content-Type: text/event-plain",
                        f"Content-Length: {length}",
                        "",
                        *body_lines,  # Unpack the list so each line is sent separately
                    ],
                )
            return

        if payload in self.commands:
            response = self.commands.get(payload)
            if callable(response):
                response = response()

            if not isinstance(response, str):
                response = str(response)

            await self.send(writer, response.splitlines())

        elif payload in dir(self):
            method = getattr(self, payload)
            if asyncio.iscoroutinefunction(method):
                await method()
            else:
                method()

    async def start(self, host, port) -> None:
        self.is_running = True
        self.client_connected = asyncio.Event()

        async def _handler(reader: StreamReader, writer: StreamWriter) -> None:
            self.client_connected.set()
            await self.handler(self, reader, writer, dial=True)

        handler = partial(self.handler, self, dial=True)  # Kept for reference if needed
        self.reader, self.writer = await open_connection(host, port)
        # Fix: the previous attempt defined _handler but didn't use it correctly with ensure_future
        # The _handler needs the reader/writer from open_connection
        self.worker = ensure_future(_handler(self.reader, self.writer))

    async def stop(self) -> None:
        self.is_running = False

        # 1. Cancel worker
        if self.worker:
            self.worker.cancel()
            try:
                await self.worker
            except (Exception, asyncio.CancelledError):
                pass

        # 2. Cancel any remaining handler tasks
        current_task = asyncio.current_task()
        for task in list(self.tasks):
            if task is not current_task and not task.done():
                task.cancel()
                try:
                    await task
                except (Exception, asyncio.CancelledError):
                    pass

        # 3. Close the writer
        if self.writer and not self.writer.is_closing():
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except (Exception, asyncio.CancelledError):
                pass

        # 4. Clean up tracked writers
        for writer in list(self.writers):
            if not writer.is_closing():
                writer.close()
            try:
                await writer.wait_closed()
            except (Exception, asyncio.CancelledError):
                pass
