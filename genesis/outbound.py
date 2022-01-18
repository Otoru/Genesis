"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""
from asyncio import StreamReader, StreamWriter
from typing import Awaitable, NoReturn

from genesis.protocol import BaseProtocol


class Session(BaseProtocol):
    """
    Session class
    -------------

    Abstracts a session established between the application and the freeswitch.
    """

    def __init__(self) -> None:
        self.context = dict()

    async def answer(self) -> Awaitable[None]:
        ...

    async def hangup(self) -> Awaitable[None]:
        ...
    
    async def playback(self, path: str, block: bool = True) -> Awaitable[None]:
        ...


class Oubound:
    """
    Oubound class
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

    async def listen(self) -> Awaitable[NoReturn]:
        ...
