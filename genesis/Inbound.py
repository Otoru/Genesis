"""
Genesis inbound
---------------

ESL implementation used for incoming connections on freeswitch.
"""
from asyncio import StreamReader, StreamWriter, open_connection, wait_for, TimeoutError
from typing import Awaitable, Optional

from genesis.exceptions import ConnectionTimeoutError


class Inbound:
    """
    Inbound class
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
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None
        self.is_connected = False
        self.password = password
        self.timeout = timeout
        self.host = host
        self.port = port

    async def connect(self) -> Awaitable[None]:
        try:
            promise = open_connection(self.host, self.port)
            self.reader, self.writer = await wait_for(promise, self.timeout)
        except TimeoutError:
            raise ConnectionTimeoutError()

    async def disconnect(self) -> Awaitable[None]:
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
