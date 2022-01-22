"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""
from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, start_server, Event
from typing import Awaitable, NoReturn, Dict, Union, List
from functools import partial
from pprint import pformat
import logging
import socket

from genesis.exceptions import UnconnectedError, SessionGoneAway
from genesis.protocol import Protocol


class Session(Protocol):
    """
    Session class
    -------------

    Abstracts a session established between the application and the freeswitch.
    """

    def __init__(self, reader: StreamReader, writer: StreamWriter) -> None:
        super().__init__()
        self.context = dict()
        self.reader = reader
        self.writer = writer
        self.is_connected = False
        self.commands = Queue()

        on_hangup = partial(self._on_hangup, self)
        self.on("CHANNEL_HANGUP", on_hangup)

    @staticmethod
    async def _on_hangup(session: Session, event: Dict) -> None:
        session.stop()

    async def __aenter__(self) -> Awaitable[Inbound]:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        await self.stop()

    async def sendmsg(
        self, command: str, application: str, data: Optional[str] = None
    ) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        cmd = f"sendmsg\ncall-command: {command}\nexecute-app-name: {application}"

        if data:
            cmd += f"\nexecute-app-arg: {data}"

        logging.debug(f"Send command to freeswitch: '{cmd}'.")
        return self.send(cmd)

    async def answer(self) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        return self.sendmsg("execute", "answer")

    async def park(self) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        return self.sendmsg("execute", "park")

    async def hangup(
        self, cause: str = "NORMAL_CLEARING"
    ) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        return self.sendmsg("execute", "hangup", cause)

    async def playback(
        self, path: str, block: bool = True
    ) -> Awaitable[Dict[str, Union[str, List[str]]]]:
        if not block:
            return self.sendmsg("execute", "playback", path)
        else:
            logging.debug("Send playback command to freeswitch with block behavior.")
            playback_command_is_complete = Event()

            async def event_handler(event):
                formated_event = pformat(event)
                logging.debug(
                    f"Recived channel execute complete event: {formated_event}"
                )

                if "variable_current_application" in event:
                    if event["variable_current_application"] == "playback":
                        playback_command_is_complete.set()

            logging.debug("Register event handler to playback complete event")
            self.on("CHANNEL_EXECUTE_COMPLETE", event_handler)

            response = await self.sendmsg("execute", "playback", path)

            logging.debug("Await playback complete event...")
            await playback_command_is_complete.wait()

            return response


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
        events: bool = True,
        linger: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.app = handler
        self.myevents = events
        self.linger = linger
        self.server = None

    async def start(self) -> Awaitable[NoReturn]:
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        async with self.server:
            logging.debug("Start application server.")
            await self.server.serve_forever()

    async def stop(self) -> Awaitable[None]:
        if self.server:
            logging.debug("Shutdown application server.")
            self.server.close()
            await self.server.wait_closed()

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> Awaitable[None]:
        async with Session(reader, writer) as session:
            logging.debug("Send command to start handle a call")
            session.context = await session.send("connect")

            if server.myevents:
                logging.debug("Send command to recive all call events")
                reply = await session.send("myevents")

            if server.linger:
                logging.debug("Send linger command to freeswitch")
                reply = await session.send("linger")

            logging.debug("Start server session handler")
            await server.app(session)
