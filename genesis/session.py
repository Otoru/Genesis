"""
Genesis Session
---------------

Abstracts a session established between the application and the freeswitch.
"""

from __future__ import annotations

from asyncio import (
    StreamReader,
    StreamWriter,
    Queue,
    Event,
    wait_for,
)
from typing import Optional, Dict, TYPE_CHECKING
from collections.abc import Callable, Coroutine
from functools import partial
from pprint import pformat
from uuid import uuid4

from genesis.protocol import Protocol
from genesis.parser import ESLEvent
from genesis.logger import logger

if TYPE_CHECKING:
    from genesis.channel import Channel


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
        self.fifo: Queue[ESLEvent] = Queue()
        self.channel: Optional["Channel"] = None

    @property
    def uuid(self) -> Optional[str]:
        return self.context.get("Unique-ID")

    async def __aenter__(self) -> Session:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        """Interface used to implement a context manager."""
        await self.stop()

    async def _awaitable_complete_command(
        self, event_uuid: str, timeout: Optional[float] = None
    ) -> Event:
        """
        Create an event that will be set when a command completes.

        Args:
            event_uuid: UUID to track the specific command execution.
            timeout: Optional timeout in seconds for the command to complete.

        Raises:
            asyncio.TimeoutError: if the command does not complete within the timeout period.

        Returns:
            Event that will be set when command completes.
        """
        semaphore = Event()

        handlers: Dict[
            str, Callable[[Session, ESLEvent], Coroutine[None, None, None]]
        ] = {}

        async def cleanup():
            for key, value in handlers.items():
                self.remove(key, value)

        async def channel_execute_complete_handler(session: Session, event: ESLEvent):
            logger.debug(f"Received channel execute complete event: {event}")

            if "Application-UUID" in event and event["Application-UUID"] == event_uuid:
                await session.fifo.put(event)
                semaphore.set()
                await cleanup()

        # Handler for CHANNEL_HANGUP_COMPLETE event to ensure we don't miss it
        # if the call is hung up before the command completes
        async def channel_hangup_complete_handler(session: Session, event: ESLEvent):
            logger.debug(f"Received hangup event: {event}")

            if (
                "Unique-ID" in event
                and session.context.get("Channel-Unique-ID", None) == event["Unique-ID"]
            ):
                await session.fifo.put(event)
                semaphore.set()
                await cleanup()

        handlers["CHANNEL_EXECUTE_COMPLETE"] = channel_execute_complete_handler
        handlers["CHANNEL_HANGUP_COMPLETE"] = channel_hangup_complete_handler

        for key, value in handlers.items():
            self.on(key, partial(value, self))

        logger.debug(f"Register event handler for Application-UUID: {event_uuid}")

        return semaphore

    async def sendmsg(
        self,
        command: str,
        application: str,
        data: Optional[str] = None,
        lock: bool = False,
        uuid: Optional[str] = None,
        event_uuid: Optional[str] = None,
        block: bool = False,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> ESLEvent:
        """
        Used to send commands from dialplan to session.

        Args:
            command: required
                Command to send to freeswitch. One of: execute, hangup, unicast, nomedia, xferext
            application: required
                Dialplan application to execute.
            data: optional
                Arguments to send to the application. If the command is 'hangup', this is the cause.
            lock: optional
                If true, lock the event.
            uuid: optional
                UUID of the call/session/channel to send the command.
            event_uuid: optional
                Adds a UUID to the execute command. In the corresponding events (CHANNEL_EXECUTE and
                CHANNEL_EXECUTE_COMPLETE), the UUID will be in the Application-UUID header.
            block: optional
                If true, wait for command completion before returning.
            headers: optional
                Additional headers to send with the command.
            timeout: optional
                Timeout for the command to complete. Just used if block is true.

        Raises:
            asyncio.TimeoutError: if the command does not complete within the timeout period.

        Returns:
            ESLEvent: The event received from FreeSWITCH after executing the command.
        """
        if uuid:
            cmd = f"sendmsg {uuid}"
        else:
            cmd = "sendmsg"

        cmd += f"\ncall-command: {command}"

        # Generate event_uuid if not provided and command is execute
        if command == "execute":
            cmd += f"\nexecute-app-name: {application}"
            if data:
                cmd += f"\nexecute-app-arg: {data}"

            event_uuid = event_uuid or str(uuid4())

            cmd += f"\nEvent-UUID: {event_uuid}"

        if lock:
            cmd += f"\nevent-lock: true"

        if command == "hangup":
            cmd += f"\nhangup-cause: {data}"

        if headers:
            for key, value in headers.items():
                cmd += f"\n{key}: {value}"

        logger.debug(f"Send command to freeswitch: '{cmd}'.")

        if block and command == "execute" and event_uuid:
            logger.debug(
                f"Waiting for command completion with Application-UUID: {event_uuid}"
            )
            # Register the event handler FIRST (returns Event object immediately)
            command_is_complete = await self._awaitable_complete_command(
                event_uuid, timeout
            )
            # Send the command (this triggers the mock to send +OK then CHANNEL_EXECUTE_COMPLETE)
            response = await self.send(cmd)
            logger.debug(
                f"Recived reponse of execute command with block: {pformat(response)}"
            )
            # Now wait for the completion event
            if timeout is not None:
                await wait_for(command_is_complete.wait(), timeout=timeout)
            else:
                await command_is_complete.wait()
            return await self.fifo.get()

        return await self.send(cmd)
