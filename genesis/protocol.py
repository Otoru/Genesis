from asyncio import StreamWriter, StreamReader, Queue
from typing import List, Awaitable, Dict, Callable

from genesis.exceptions import UnconnectedError
from genesis.parser import parse


class BaseProtocol:
    @staticmethod
    async def send(writer: StreamWriter, lines: List[str]) -> Awaitable[None]:
        """Method used to send commands to or freeswitch."""
        if not writer.is_closing():
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

            writer.write("\n".encode("utf-8"))
            await writer.drain()
