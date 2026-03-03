"""
Genesis Session
---------------

Abstracts a session established between the application and the freeswitch.
"""

from __future__ import annotations

from asyncio import Event, Queue, StreamReader, StreamWriter, wait_for
from functools import partial
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from uuid import uuid4

from genesis.observability import logger
from genesis.protocol import Protocol
from genesis.protocol.parser import ESLEvent

if TYPE_CHECKING:
    from genesis.channel import Channel


def _build_sendmsg_cmd(
    command: str,
    application: str,
    data: Optional[str] = None,
    lock: bool = False,
    uuid: Optional[str] = None,
    event_uuid: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Optional[str]]:
    """Build sendmsg command string and return (cmd, event_uuid)."""
    cmd = f"sendmsg {uuid}" if uuid else "sendmsg"
    cmd += f"\ncall-command: {command}"

    if command == "execute":
        cmd += f"\nexecute-app-name: {application}"
        if data:
            cmd += f"\nexecute-app-arg: {data}"
        event_uuid = event_uuid or str(uuid4())
        cmd += f"\nEvent-UUID: {event_uuid}"

    if lock:
        cmd += "\nevent-lock: true"

    if command == "hangup":
        cmd += f"\nhangup-cause: {data}"

    if headers:
        for key, value in headers.items():
            cmd += f"\n{key}: {value}"

    return (cmd, event_uuid if command == "execute" else None)


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
        self.context: Dict[str, str] = {}
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

    async def __aexit__(self, *args: object, **kwargs: object) -> None:
        """Interface used to implement a context manager."""
        await self.stop()

    def _awaitable_complete_command(
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
        registrations: List[Tuple[Optional[str], str, Any]] = (
            []
        )  # (channel_uuid?, key, handler)

        def cleanup() -> None:
            for channel_uid, key, handler in registrations:
                if channel_uid is None:
                    self.remove(key, handler)
                else:
                    self.unregister_channel_handler(channel_uid, key, handler)

        async def execute_complete_handler(session: Session, event: ESLEvent) -> None:
            logger.debug("Received channel execute complete event: %s", event)
            if event.get("Application-UUID") == event_uuid:
                await session.fifo.put(event)
                semaphore.set()
                cleanup()

        async def hangup_complete_handler(session: Session, event: ESLEvent) -> None:
            logger.debug("Received hangup event: %s", event)
            if session.context.get("Channel-Unique-ID") == event.get("Unique-ID"):
                await session.fifo.put(event)
                semaphore.set()
                cleanup()

        handlers = {
            "CHANNEL_EXECUTE_COMPLETE": execute_complete_handler,
            "CHANNEL_HANGUP_COMPLETE": hangup_complete_handler,
        }

        channel_uuid = self.uuid
        for key, handler_fn in handlers.items():
            bound = partial(handler_fn, self)
            if channel_uuid:
                self.register_channel_handler(channel_uuid, key, bound)
                registrations.append((channel_uuid, key, bound))
            else:
                self.on(key, bound)
                registrations.append((None, key, bound))

        logger.debug("Register event handler for Application-UUID: %s", event_uuid)
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
        cmd, resolved_event_uuid = _build_sendmsg_cmd(
            command, application, data, lock, uuid, event_uuid, headers
        )
        logger.debug("Send command to freeswitch: '%s'.", cmd)

        if block and command == "execute" and resolved_event_uuid:
            logger.debug(
                "Waiting for command completion with Application-UUID: %s",
                resolved_event_uuid,
            )
            command_is_complete = self._awaitable_complete_command(
                resolved_event_uuid, timeout
            )
            response = await self.send(cmd)
            logger.debug(
                "Received response of execute command with block: %s",
                response,
            )
            if timeout is not None:
                await wait_for(command_is_complete.wait(), timeout=timeout)
            else:
                await command_is_complete.wait()
            return await self.fifo.get()

        return await self.send(cmd)
