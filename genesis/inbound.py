"""
Genesis inbound
---------------
ESL implementation used for incoming connections on freeswitch.
"""

from __future__ import annotations

from asyncio import open_connection, TimeoutError, wait_for
from typing import Awaitable

from genesis.exceptions import ConnectionTimeoutError, AuthenticationError
from genesis.protocol import Protocol
from genesis.logger import logger


class Inbound(Protocol):
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
        super().__init__()
        self.password = password
        self.timeout = timeout
        self.host = host
        self.port = port

    async def __aenter__(self) -> Inbound:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        """Interface used to implement a context manager."""
        await self.stop()

    async def authenticate(self) -> None:
        """Authenticates to the freeswitch server. Raises an exception on failure."""
        await self.authentication_event.wait()
        logger.debug("Send command to authenticate inbound ESL connection.")
        response = await self.send(f"auth {self.password}")

        if response["Reply-Text"] != "+OK accepted":
            logger.debug("Freeswitch said the passed password is incorrect.")
            raise AuthenticationError("Invalid password")

    async def start(self) -> None:
        """Initiates an authenticated connection to a freeswitch server."""
        try:
            promise = open_connection(self.host, self.port)
            self.reader, self.writer = await wait_for(promise, self.timeout)
        except TimeoutError:
            logger.debug("A timeout occurred when trying to connect to the freeswitch.")
            raise ConnectionTimeoutError()

        await super().start()
        await self.authenticate()
