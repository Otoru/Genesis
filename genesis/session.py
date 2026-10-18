"""
Genesis Session
---------------

Abstracts a session established between the application and the freeswitch.
"""

from __future__ import annotations

import contextlib
import time
from asyncio import (
    FIRST_COMPLETED,
    CancelledError,
    Future,
    StreamReader,
    StreamWriter,
    Task,
    get_running_loop,
    wait,
    wait_for,
)
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast
from uuid import uuid4

from genesis.exceptions import CommandStage, SessionGoneAway
from genesis.observability import logger
from genesis.protocol import Protocol
from genesis.protocol.parser import ESLEvent
from genesis.protocol.routing.dispatcher import run_on_loop
from genesis.protocol.metrics import (
    session_command_duration,
    session_commands_counter,
    safe_add,
    safe_record,
    ObservingSpan,
)

if TYPE_CHECKING:
    from genesis.channel import Channel


def _rejected(event: ESLEvent) -> bool:
    """True when FreeSWITCH refused the command instead of accepting it."""
    reply = _one(event.get("Reply-Text")) or ""
    return reply.startswith("-ERR")


def _one(value: Any) -> Optional[str]:
    """Return one string header value."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return value
    return None


class _ExecutionWait:
    """Completion of one ``execute``, keyed by ``Application-UUID``.

    Register with :meth:`install` before the command is written. A later
    ``CHANNEL_EXECUTE_COMPLETE`` for another UUID does not complete this wait.
    """

    def __init__(self, application_uuid: str, hangup_uuid: Optional[str]) -> None:
        self.application_uuid = application_uuid
        self.hangup_uuid = hangup_uuid
        self.future: Future[ESLEvent] = get_running_loop().create_future()
        self._registrations: List[Tuple[Optional[str], str, Any]] = []
        self._protocol: Optional[Protocol] = None

    def install(self, protocol: Protocol, channel_uuid: Optional[str]) -> None:
        """Listen for this command's completion and for hangup of its channel."""
        self._protocol = protocol

        def on_complete(event: ESLEvent) -> None:
            if _one(event.get("Application-UUID")) != self.application_uuid:
                return
            self.succeed(event)

        def on_hangup(event: ESLEvent) -> None:
            if self.hangup_uuid is None:
                return
            if _one(event.get("Unique-ID")) != self.hangup_uuid:
                return
            self.fail(SessionGoneAway())

        self._bind(
            protocol,
            channel_uuid,
            "CHANNEL_EXECUTE_COMPLETE",
            run_on_loop(on_complete),
        )
        self._bind(
            protocol,
            channel_uuid,
            "CHANNEL_HANGUP_COMPLETE",
            run_on_loop(on_hangup),
        )
        logger.debug(
            "Register event handler for Application-UUID: %s", self.application_uuid
        )

    def uninstall(self) -> None:
        """Drop handlers. A late event for this UUID is ignored."""
        protocol = self._protocol
        if protocol is None:
            return
        for channel_uuid, key, handler in self._registrations:
            if channel_uuid is None:
                protocol.remove(key, handler)
            else:
                protocol.unregister_channel_handler(channel_uuid, key, handler)
        self._registrations.clear()

    def succeed(self, event: ESLEvent) -> None:
        if self.future.done():
            return
        self.future.set_result(event)
        self.uninstall()

    def fail(self, exc: BaseException) -> None:
        if self.future.done():
            return
        self.future.set_exception(exc)
        self.uninstall()

    def abandon(self) -> None:
        """Unregister and drop a result nobody is waiting for."""
        self.uninstall()
        if not self.future.done():
            self.future.cancel()
        elif not self.future.cancelled():
            self.future.exception()

    def _bind(
        self,
        protocol: Protocol,
        channel_uuid: Optional[str],
        key: str,
        handler: Any,
    ) -> None:
        if channel_uuid:
            protocol.register_channel_handler(channel_uuid, key, handler)
            self._registrations.append((channel_uuid, key, handler))
            return
        protocol.on(key, handler)
        self._registrations.append((None, key, handler))


def _install_execution_wait(
    protocol: Protocol,
    application_uuid: str,
    channel_uuid: Optional[str],
    hangup_uuid: Optional[str],
) -> _ExecutionWait:
    """Register one execution wait before the matching command is sent."""
    wait = _ExecutionWait(application_uuid, hangup_uuid)
    wait.install(protocol, channel_uuid)
    return wait


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
        self.channel: Optional["Channel"] = None
        self._loss_tasks: set[Task[None]] = set()

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

    def _hangup_uuid(self) -> Optional[str]:
        return _one(self.context.get("Channel-Unique-ID")) or self.uuid

    async def _await_execution(
        self, execution: _ExecutionWait, timeout: Optional[float]
    ) -> ESLEvent:
        """Wait for this execute, or for connection loss after the ack."""
        lost: Task[None] = get_running_loop().create_task(
            self.wait_lost(CommandStage.ACCEPTED)
        )
        self._loss_tasks.add(lost)
        try:
            race = wait(
                cast(List[Future[Any]], [execution.future, lost]),
                return_when=FIRST_COMPLETED,
            )
            if timeout is not None:
                done, _pending = await wait_for(race, timeout)
            else:
                done, _pending = await race
            if execution.future in done:
                return execution.future.result()
            await lost
            raise AssertionError("connection loss did not fail the completion wait")
        finally:
            self._loss_tasks.discard(lost)
            if not lost.done():
                lost.cancel()
                with contextlib.suppress(CancelledError):
                    await lost
            elif not lost.cancelled():
                lost.exception()

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
            SessionGoneAway: the channel hung up while this execute was still running.
            ConnectionLost: the ESL connection closed. The stage is ``NOT_SENT``
                before write, the protocol's own stage while the ack is outstanding,
                and ``ACCEPTED`` while waiting for completion. A local ``stop()``
                is ``NOT_SENT`` for both ``block`` values.
            ChannelError: ``block`` is true and a negative filter hides
                ``CHANNEL_EXECUTE_COMPLETE``. The filter is not removed.
            asyncio.CancelledError: the caller cancelled this wait.

        Returns:
            ESLEvent: The event received from FreeSWITCH after executing the command.
        """
        cmd, resolved_event_uuid = _build_sendmsg_cmd(
            command, application, data, lock, uuid, event_uuid, headers
        )
        logger.debug("Send command to freeswitch: '%s'.", cmd)
        self.raise_if_lost(CommandStage.NOT_SENT)

        start_time = time.perf_counter()
        opened = ObservingSpan.open(
            "session.sendmsg",
            {
                "channel.uuid": self.uuid or "unknown",
                "application.name": application,
                "application.uuid": resolved_event_uuid or "unknown",
                "application.block": str(block),
            },
        )
        safe_add_cmd_attrs = {"application.name": application}
        try:
            if block and command == "execute" and resolved_event_uuid:
                self.subscriptions.require_completion_visible(self.uuid or "")
                logger.debug(
                    "Waiting for command completion with Application-UUID: %s",
                    resolved_event_uuid,
                )
                execution = _install_execution_wait(
                    self, resolved_event_uuid, self.uuid, self._hangup_uuid()
                )
                try:
                    response = await self.send(cmd)
                    logger.debug(
                        "Received response of execute command with block: %s",
                        response,
                    )
                    if _rejected(response):
                        result = response
                    else:
                        waiting = ObservingSpan.open(
                            "session.await_complete",
                            {
                                "channel.uuid": self.uuid or "unknown",
                                "application.uuid": resolved_event_uuid,
                            },
                        )
                        try:
                            result = await self._await_execution(execution, timeout)
                        finally:
                            waiting.close()
                finally:
                    execution.abandon()
            else:
                result = await self.send(cmd)
            safe_record(
                session_command_duration,
                time.perf_counter() - start_time,
                attributes=safe_add_cmd_attrs,
            )
            safe_add(session_commands_counter, 1, attributes=safe_add_cmd_attrs)
            return result
        finally:
            opened.close()
