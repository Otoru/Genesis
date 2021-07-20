"""
Genesis Protocol
----------------

Here we will group what is common to the ESL client for inbound and outbound connections.
"""
from asyncio import StreamWriter, StreamReader, Queue
from typing import List, Awaitable, Dict, Callable

from genesis.exceptions import UnconnectedError
from genesis.parser import parse


class BaseProtocol:
    """
    BaseProtocol Class
    ------------------

    Contains methods common to inbound and outbound connectors.
    """

    @staticmethod
    async def send(writer: StreamWriter, lines: List[str]) -> Awaitable[None]:
        """Method used to send commands to or freeswitch."""
        if not writer.is_closing():
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

            writer.write("\n".encode("utf-8"))
            await writer.drain()
