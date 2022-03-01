"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""
from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, start_server, Event
from typing import Awaitable, NoReturn, Dict, Union, List
from functools import partial
import logging
import socket

from genesis.exceptions import UnconnectedError, SessionGoneAway
from genesis.protocol import Protocol
from genesis import types


class Session(Protocol):
    """
    Session class
    -------------

    Abstracts a session established between the application and the freeswitch.

    Attributes:
    - reader: required
        StreamReader used to read incoming information.
    - writer: required
        StreamWriter used to send information to freeswitch.
    """

    def __init__(self, reader: StreamReader, writer: StreamWriter) -> None:
        super().__init__()
        self.context = dict()
        self.reader = reader
        self.writer = writer
        self.commands = Queue()

    async def __aenter__(self) -> Awaitable[Inbound]:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        """Interface used to implement a context manager."""
        await self.stop()

    async def _awaitable_complete_command(self, application: str) -> Event:
        """Used to build an event associated with the completion of a command."""
        semaphore = Event()

        async def handler(event: types.Event):
            logging.debug(f"Recived channel execute complete event: {event}")

            if "variable_current_application" in event:
                if event["variable_current_application"] == application:
                    semaphore.set()

        logging.debug(f"Register event handler to {application} complete event")
        self.on("CHANNEL_EXECUTE_COMPLETE", handler)

        return semaphore

    async def sendmsg(
        self, command: str, application: str, data: Optional[str] = None
    ) -> Awaitable[types.Event]:
        """Used to send commands from dialplan to session."""
        cmd = f"sendmsg\ncall-command: {command}\nexecute-app-name: {application}"

        if data:
            cmd += f"\nexecute-app-arg: {data}"

        logging.debug(f"Send command to freeswitch: '{cmd}'.")
        return self.send(cmd)

    async def answer(self) -> Awaitable[types.Event]:
        """Answer the call associated with the session."""
        return self.sendmsg("execute", "answer")

    async def park(self) -> Awaitable[types.Event]:
        """Move session-associated call to park."""
        return self.sendmsg("execute", "park")

    async def hangup(self, cause: str = "NORMAL_CLEARING") -> Awaitable[types.Event]:
        """Hang up the call associated with the session."""
        return self.sendmsg("execute", "hangup", cause)

    async def playback(self, path: str, block=True) -> Awaitable[types.Event]:
        """Requests the freeswitch to play an audio."""
        if not block:
            return self.sendmsg("execute", "playback", path)

        logging.debug("Send playback command to freeswitch with block behavior.")
        playback_command_is_complete = self._awaitable_complete_command("playback")
        response = await self.sendmsg("execute", "playback", path)

        logging.debug("Await playback complete event...")
        await playback_command_is_complete.wait()

        return response

    async def say(
        self,
        text: str,
        module="en",
        lang: Optional[str] = None,
        kind: str = "NUMBER",
        method: str = "pronounced",
        gender: str = "FEMININE",
        block=True,
        timeout=30,
    ) -> Awaitable[types.Event]:
        """The say application will use the pre-recorded sound files to read or say things."""
        if lang:
            module += f":{lang}"

        arguments = f"{module} {kind} {method} {gender} {text}"

        if not block:
            return self.sendmsg("execute", "say", arguments)

        logging.debug("Send say command to freeswitch with block behavior.")
        say_command_is_complete = self._awaitable_complete_command("say")
        response = await self.sendmsg("execute", "say", arguments)

        logging.debug("Await say complete event...")
        await say_command_is_complete.wait()

        return response

    async def play_and_get_digits(
        self,
        terminators,
        file,
        tries=1,
        timeout=30,
        block=True,
        min_digits=0,
        max_digits=128,
        response_timeout=30,
        regexp: Optional[str] = None,
        var_name: Optional[str] = None,
        invalid_file: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
    ) -> Awaitable[types.Event]:
        ...


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
        """Start the application server."""
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        async with self.server:
            logging.debug("Start application server.")
            await self.server.serve_forever()

    async def stop(self) -> Awaitable[None]:
        """Terminate the application server."""
        if self.server:
            logging.debug("Shutdown application server.")
            self.server.close()
            await self.server.wait_closed()

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> Awaitable[None]:
        """Method used to process new connections."""
        async with Session(reader, writer) as session:
            logging.debug("Send command to start handle a call")
            session.context = await session.send("connect")

            if server.myevents:
                logging.debug("Send command to recive all call events")
                reply = await session.send("myevents")

            if server.linger:
                logging.debug("Send linger command to freeswitch")
                reply = await session.send("linger")
                session.is_lingering = True

            logging.debug("Start server session handler")
            await server.app(session)
