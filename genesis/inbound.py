"""
Genesis inbound
---------------

ESL implementation used for incoming connections on freeswitch.
"""
from asyncio import StreamReader, StreamWriter, open_connection, wait_for, TimeoutError
from typing import Awaitable, Optional, Dict

from genesis.exceptions import ConnectionTimeoutError, AuthenticationError


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

    async def __aenter__(self) -> Awaitable[Inbound]:
        """Interface used to implement a context manager."""
        await self.connect()
        return self

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        await self.disconnect()

    async def send(self, message: str) -> Awaitable[Dict[str, str]]:
        # TODO(Vitor): Define how our client will actually communicate with freeswitch.
        raise NotImplementedError()

    async def authenticate(self) -> Awaitable[None]:
        """Authenticates to the freeswitch server. Raises an exception on failure."""
        response = await self.send(f"auth {self.password}")

        if response["Reply-Text"] != "+OK accepted":
            raise AuthenticationError("Invalid password")

    async def connect(self) -> Awaitable[None]:
        """Initiates an authenticated connection to a freeswitch server."""
        try:
            promise = open_connection(self.host, self.port)
            self.reader, self.writer = await wait_for(promise, self.timeout)
        except TimeoutError:
            raise ConnectionTimeoutError()

        await self.authenticate()

    async def disconnect(self) -> Awaitable[None]:
        """Terminates connection to a freeswitch server."""
        await self.send("exit")
