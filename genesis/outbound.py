"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""

from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, start_server, Event
from collections.abc import Callable, Coroutine
from typing import Awaitable, NoReturn, Optional, Union, Dict
from functools import partial
import socket

from genesis.protocol import Protocol
from genesis.parser import ESLEvent
from genesis.logger import logger


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
        self.context: Dict[str, str] = dict()
        self.reader = reader
        self.writer = writer
        self.fifo = Queue()

    async def __aenter__(self) -> Session:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        """Interface used to implement a context manager."""
        await self.stop()

    async def _awaitable_complete_command(self, application: str) -> Event:
        """
        Create an event that will be set when a command completes.

        Args:
            application: Name of the application to wait for completion

        Returns:
            Event that will be set when command completes
        """
        semaphore = Event()

        async def handler(session: Session, event: ESLEvent):
            logger.debug(f"Recived channel execute complete event: {event}")

            if "variable_current_application" in event:
                if event["variable_current_application"] == application:
                    await session.fifo.put(event)
                    semaphore.set()
                    self.remove("CHANNEL_EXECUTE_COMPLETE", handler)

        logger.debug(f"Register event handler to {application} complete event")
        self.on("CHANNEL_EXECUTE_COMPLETE", partial(handler, self))

        return semaphore

    async def sendmsg(
        self, command: str, application: str, data: Optional[str] = None, lock=False
    ) -> ESLEvent:
        """Used to send commands from dialplan to session."""
        cmd = f"sendmsg\ncall-command: {command}\nexecute-app-name: {application}"

        if data:
            cmd += f"\nexecute-app-arg: {data}"

        if lock:
            cmd += f"\nevent-lock: true"

        logger.debug(f"Send command to freeswitch: '{cmd}'.")
        return await self.send(cmd)

    async def answer(self) -> ESLEvent:
        """Answer the call associated with the session."""
        return await self.sendmsg("execute", "answer")

    async def park(self) -> ESLEvent:
        """Move session-associated call to park."""
        return await self.sendmsg("execute", "park")

    async def hangup(self, cause: str = "NORMAL_CLEARING") -> ESLEvent:
        """Hang up the call associated with the session."""
        return await self.sendmsg("execute", "hangup", cause)

    async def playback(self, path: str, block=True) -> ESLEvent:
        """Requests the freeswitch to play an audio."""
        if not block:
            return await self.sendmsg("execute", "playback", path)

        logger.debug("Send playback command to freeswitch with block behavior.")
        command_is_complete = await self._awaitable_complete_command("playback")
        response = await self.sendmsg("execute", "playback", path)

        logger.debug("Await playback complete event...")
        await command_is_complete.wait()

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
    ) -> ESLEvent:
        """The say application will use the pre-recorded sound files to read or say things."""
        if lang:
            module += f":{lang}"

        arguments = f"{module} {kind} {method} {gender} {text}"
        logger.debug(f"Arguments used in say command: {arguments}")

        if not block:
            return await self.sendmsg("execute", "say", arguments)

        logger.debug("Send say command to freeswitch with block behavior.")
        command_is_complete = await self._awaitable_complete_command("say")
        response = await self.sendmsg("execute", "say", arguments)
        logger.debug(f"Response of say command: {response}")

        logger.debug("Await say complete event...")
        await command_is_complete.wait()

        event = await self.fifo.get()
        logger.debug(f"Execute complete event recived: {event}")

        return event

    async def play_and_get_digits(
        self,
        tries,
        timeout,
        terminators,
        file,
        minimal=0,
        maximum=128,
        block=True,
        regexp: Optional[str] = None,
        var_name: Optional[str] = None,
        invalid_file: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
    ) -> ESLEvent:
        formatter = lambda value: "" if value is None else str(value)
        ordered_arguments = [
            minimal,
            maximum,
            tries,
            timeout,
            terminators,
            file,
            invalid_file,
            var_name,
            regexp,
            digit_timeout,
            transfer_on_failure,
        ]
        formated_ordered_arguments = map(formatter, ordered_arguments)
        arguments = " ".join(formated_ordered_arguments)
        logger.debug(f"Arguments used in play_and_get_digits command: {arguments}")

        if not block:
            return await self.sendmsg("execute", "play_and_get_digits", arguments)

        logger.debug(
            "Send play_and_get_digits command to freeswitch with block behavior."
        )
        command_is_complete = await self._awaitable_complete_command(
            "play_and_get_digits"
        )
        response = await self.sendmsg("execute", "play_and_get_digits", arguments)
        logger.debug(f"Response of play_and_get_digits command: {response}")

        logger.debug("Await play_and_get_digits complete event...")
        await command_is_complete.wait()

        event = await self.fifo.get()
        logger.debug(f"Execute complete event recived: {event}")

        return event


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
        handler: Union[Callable, Coroutine],
        host: str = "127.0.0.1",
        port: int = 9000,
        events: bool = True,
        linger: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.app = handler
        self.myevents = events
        self.linger = linger
        self.server = None

    async def start(self, block: bool = True) -> None:
        """Start the application server."""
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        address = f"{self.host}:{self.port}"
        logger.info(f"Start application server and listen on '{address}'.")
        if block:
            await self.server.serve_forever()
        else:
            await self.server.start_serving()

    async def stop(self) -> None:
        """Terminate the application server."""
        if self.server:
            logger.debug("Shutdown application server.")
            self.server.close()
            await self.server.wait_closed()

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> None:
        """Method used to process new connections."""
        async with Session(reader, writer) as session:
            logger.debug("Send command to start handle a call")
            session.context = await session.send("connect")

            if server.myevents:
                logger.debug("Send command to receive all call events")
                await session.send("myevents")

            if server.linger:
                logger.debug("Send linger command to freeswitch")
                await session.send("linger")
                session.is_lingering = True

            logger.debug("Start server session handler")
            await server.app(session)
