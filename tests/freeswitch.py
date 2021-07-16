"""
Freeswitch module
-----------------

Aggregate created to provide the necessary material to simulate a freeswitrch server in test environments.


    Example:

    async with freeswitch.Server("0.0.0.0", 8021, "Cluecon"):
        ...

Remembering that we only simulate the communication via ESL and not the processing of SIP calls.
"""
from asyncio import StreamReader, StreamWriter, start_server, CancelledError
from typing import List, Awaitable, Callable
from copy import copy

STATUS = """UP 0 years, 80 days, 8 hours, 25 minutes, 5 seconds, 869 milliseconds, 87 microseconds
FreeSWITCH (Version 1.10.3-release git e52b1a8 2020-09-09 12:16:24Z 64bit) is ready
7653 session(s) since startup
0 session(s) - peak 2, last 5min 0
0 session(s) per Sec out of max 30, peak 14, last 5min 0
1000 session(s) max
min idle cpu 0.00/99.00
Current Stack Size/Max 240K/8192K
"""

CONSOSE = "+OK console log level set to DEBUG"

COLORIZE = "+OK console color enabled"

VERSION = "FreeSWITCH Version 1.10.3-release+git~20200909T121624Z~e52b1a859b~64bit (git e52b1a8 2020-09-09 12:16:24Z 64bit)"

UPTIME = "6943047"

COMMANDS = {
    "uptime": UPTIME,
    "version": VERSION,
    "api status": STATUS,
    "api console loglevel": CONSOSE,
    "api console colorize": COLORIZE,
}


class Server:
    """
    Server class
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

    def __init__(self, host: str, port: int, password: str) -> None:
        self.password = password
        self.is_running = False
        self.server = None
        self.host = host
        self.port = port

    async def stop(self) -> Awaitable[None]:
        """Stop current server."""
        self.is_running = False
        self.server.close()

        await self.server.wait_closed()

    async def __aenter__(self) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        self.is_running = True
        handler = await self.factory()
        self.server = await start_server(handler, self.host, self.port)
        try:
            await self.server.serve_forever()
        except CancelledError:
            pass

    async def __aexit__(self, *args, **kwargs):
        """Interface used to implement a context manager."""
        await self.stop()

    @staticmethod
    async def send(writer: StreamWriter, lines: List[str]) -> Awaitable[None]:
        """Given a line-separated message, we send the ESL client."""
        for line in lines:
            writer.write((line + "\n").encode("utf-8"))

        writer.write("\n".encode("utf-8"))
        await writer.drain()

    async def command(self, writer: StreamWriter, command: str) -> Awaitable[None]:
        """Response an ESL command received."""
        await self.send(
            writer, ["Content-Type: command/reply", f"Reply-Text: {command}"]
        )

    async def api(self, writer: StreamWriter, content: List[str]) -> Awaitable[None]:
        """Response an API statement received via ESL."""
        await self.send(
            writer,
            ["Content-Type: api/response", f"Content-Length: {len(''.join(content))}"],
        )
        await self.send(writer, content.split())

    async def disconnect(self, writer: StreamWriter) -> Awaitable[None]:
        """Appropriately closes an ESL connection."""
        await self.send(
            writer, ["Content-Type: text/disconnect-notice", "Content-Length: 67"]
        )
        await self.send(
            writer,
            ["Disconnected, goodbye.", "See you at ClueCon! http://www.cluecon.com/"],
        )
        self.is_running = False
        self.server.close()

    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        """Given an ESL event, we process it."""
        payload = copy(request)

        if payload.startswith("auth"):
            received_password = payload.split().pop().strip()

            if self.password == received_password:
                await self.command(writer, "+OK accepted")

            else:
                await self.command(writer, "-ERR invalid")
                await self.disconnect(writer)

        elif payload == "exit":
            await self.command(writer, "+OK bye")
            await self.disconnect(writter)
            await self.stop()

        elif payload in COMMANDS:
            response = COMMANDS.get(payload)

            if payload.startswith("api"):
                await self.api(writer, response)

            else:
                await self.command(writer, response)

        elif payload.startswith("api"):
            command = payload.replace("api", "").split().pop().strip()
            await self.command(writer, f"-ERR {command} command not found")

        else:
            await self.command(writer, "-ERR command not found")

    async def factory(self) -> Callable[[StreamReader, StreamWriter], Awaitable[None]]:
        """Returns a handler to handle new ESL-based connections."""

        async def reading(reader: StreamReader, writer: StreamWriter) -> None:
            await self.send(writer, ["Content-Type: auth/request"])

            while self.is_running:
                buffer = ""
                request = None

                while self.is_running:
                    try:
                        content = await reader.read(1)

                    except Exception as exc:
                        self.is_running = False
                        writer.close()
                        break

                    buffer += content.decode("utf-8")

                    if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                        request = buffer
                        break

                request = buffer.strip()

                if not request and not self.is_running:
                    break

                await self.process(writer, request)

        return reading
