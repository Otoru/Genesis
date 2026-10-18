"""Loopback ESL server. Many connections, one listener."""

import asyncio
from typing import Dict, List, Optional, Sequence, Set, Tuple
from uuid import uuid4

from tests.simulator.channels import ChannelRecord
from tests.simulator.codec import ESLFrame, Header
from tests.simulator.connection import Connection, PendingExecution
from tests.simulator.faults import Fault
from tests.simulator.journal import Journal
from tests.simulator.messages import event_plain
from tests.simulator.scenario import ScenarioDriver


def _execution_target(pending: PendingExecution, connection_id: Optional[str]) -> str:
    if connection_id is not None:
        return connection_id
    return pending.connection_id


def _execution_headers(
    pending: PendingExecution, name: str, response: Optional[str] = None
) -> Tuple[Header, ...]:
    headers: List[Header] = [
        ("Event-Name", name),
        ("Application", pending.application),
        ("Application-UUID", pending.event_uuid),
    ]
    if pending.data:
        headers.append(("Application-Data", pending.data))
    if response is not None:
        headers.append(("Application-Response", response))
    if pending.channel_uuid:
        headers.append(("Unique-ID", pending.channel_uuid))
    return tuple(headers)


class Simulator:
    """Inbound ESL listener and outbound dialplan peer on ``127.0.0.1``."""

    def __init__(self, password: str) -> None:
        self.password = password
        self.journal = Journal()
        self.channels: Dict[str, str] = {}
        self.records: Dict[str, ChannelRecord] = {}
        self.hangups: List[Tuple[str, str]] = []
        self.sessions: Dict[str, str] = {}
        self._pending_fault: Optional[Fault] = None
        self._arm_caught: Optional[asyncio.Event] = None
        self._executions: asyncio.Queue[PendingExecution] = asyncio.Queue()
        self.open_executions: Dict[str, PendingExecution] = {}
        self.scenario = ScenarioDriver(self.journal, self.emit)
        self.scenario.bind_preempt(self._preempt)
        self._server: Optional[asyncio.AbstractServer] = None
        self._connections: Dict[str, Connection] = {}
        self._tasks: Set[asyncio.Task[None]] = set()
        self._starting = False
        self._seq = 0

    async def __aenter__(self) -> "Simulator":
        await self.start()
        return self

    async def __aexit__(self, *args: object) -> None:
        del args
        await self.close()

    async def listen(self) -> None:
        await self.start()

    async def start(self) -> None:
        if self._starting or self._server is not None:
            raise RuntimeError("simulator is already listening")
        self._starting = True
        try:
            self._server = await asyncio.start_server(self._on_client, "127.0.0.1", 0)
        except BaseException:
            self._starting = False
            raise
        self._starting = False

    async def close(self) -> None:
        server = self._server
        self._server = None
        self._starting = False
        if server is not None:
            server.close()
        current = asyncio.current_task()
        for task in list(self._tasks):
            if task is not current and not task.done():
                task.cancel()
        for task in list(self._tasks):
            if task is current:
                continue
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks.clear()
        for conn in list(self._connections.values()):
            await conn.aclose()
        self._connections.clear()
        if server is not None:
            await server.wait_closed()

    @property
    def host(self) -> str:
        return "127.0.0.1"

    @property
    def port(self) -> int:
        server = self._server
        if not isinstance(server, asyncio.Server) or not server.sockets:
            raise RuntimeError("simulator is not listening")
        return int(server.sockets[0].getsockname()[1])

    @property
    def connection_ids(self) -> Tuple[str, ...]:
        return tuple(self._connections)

    def connection(self, connection_id: str) -> Connection:
        try:
            return self._connections[connection_id]
        except KeyError as exc:
            raise KeyError(connection_id) from exc

    async def emit(
        self,
        headers: Sequence[Header],
        *,
        body: bytes = b"",
        connection_id: Optional[str] = None,
    ) -> None:
        frame = event_plain(headers, body)
        for conn in self._targets(connection_id):
            if conn.authed and conn.wants(tuple(headers)):
                await conn.send_event(frame)

    async def connect_dialplan(
        self,
        host: str,
        port: int,
        *,
        full: bool = True,
        session_uuid: Optional[str] = None,
    ) -> str:
        reader, writer = await asyncio.open_connection(host, port)
        connection_id = self._next_id()
        conn = self._make_connection(
            connection_id,
            reader,
            writer,
            outbound=True,
            full=full,
            session_uuid=session_uuid or str(uuid4()),
        )
        self._connections[connection_id] = conn
        task = asyncio.create_task(self._run(conn))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return connection_id

    def seed_channel(
        self,
        channel_uuid: str,
        *,
        name: str = "",
        state: str = "CS_EXECUTE",
        call_state: str = "ACTIVE",
        answer_state: str = "answered",
        application: str = "",
        application_data: str = "",
        variables: Optional[Dict[str, str]] = None,
    ) -> None:
        """Remember a channel that already exists. Does not emit lifecycle events."""
        self.channels[channel_uuid] = name
        self.records[channel_uuid] = ChannelRecord(
            channel_uuid,
            name=name,
            state=state,
            call_state=call_state,
            answer_state=answer_state,
            application=application,
            application_data=application_data,
            variables=variables,
        )

    def disappear_after(self, channel_uuid: str, lookups: int) -> None:
        """Drop the channel once ``lookups`` exists/dump calls have succeeded.

        ``0`` makes the next lookup answer as absent and remove the row.
        ``1`` lets the next lookup succeed and removes the row on the one after.
        """
        if lookups < 0:
            raise ValueError("lookups must be >= 0")
        record = self.records.get(channel_uuid)
        if record is None:
            if channel_uuid not in self.channels:
                raise KeyError(channel_uuid)
            record = ChannelRecord(channel_uuid, name=self.channels[channel_uuid])
            self.records[channel_uuid] = record
        record.lookups_remaining = lookups

    async def next_execution(self, timeout: float = 2.0) -> PendingExecution:
        """Wait until a ``sendmsg`` execute has been recorded."""
        return await asyncio.wait_for(self._executions.get(), timeout)

    async def start_execution(
        self, pending: PendingExecution, connection_id: Optional[str] = None
    ) -> None:
        """Emit ``CHANNEL_EXECUTE`` from the recorded command.

        ``connection_id`` chooses the socket. The default is the socket that
        sent ``sendmsg``. The call does not run by itself when that socket
        drops. Pass the replacement socket after a new login.
        """
        self._remember_application(pending)
        await self.emit(
            _execution_headers(pending, "CHANNEL_EXECUTE"),
            connection_id=_execution_target(pending, connection_id),
        )

    async def complete_execution(
        self, pending: PendingExecution, connection_id: Optional[str] = None
    ) -> None:
        """Emit ``CHANNEL_EXECUTE_COMPLETE`` using the recorded ``Event-UUID``.

        The application UUID is the one copied from the command. Callers do
        not pass a second UUID. ``start_execution`` is separate so a timeout
        or a dropped socket can leave the execution in ``open_executions``.
        """
        self._remember_application(pending)
        self.open_executions.pop(pending.event_uuid, None)
        await self.emit(
            _execution_headers(pending, "CHANNEL_EXECUTE_COMPLETE", "_none_"),
            connection_id=_execution_target(pending, connection_id),
        )

    def arm_next(self, fault: Fault) -> asyncio.Event:
        """Apply ``fault`` to the next inbound peer before it reads a command.

        ``Fault.STALL_READS`` is set before the read loop, after the
        ``auth/request`` greeting. The returned event is set when that peer
        discards its first command. No reply is written for that command.
        """
        if self._pending_fault is not None:
            raise RuntimeError("a fault is already armed for the next inbound peer")
        self._pending_fault = fault
        caught = asyncio.Event()
        self._arm_caught = caught
        return caught

    async def fail(self, fault: Fault, connection_id: Optional[str] = None) -> None:
        conn = self._single(connection_id)
        if fault is Fault.STALL_READS:
            conn.stalled = True
            conn.stall_caught.clear()
            conn._resume = asyncio.Event()
            try:
                await conn._resume.wait()
            finally:
                conn.stalled = False
                conn._resume.set()
            return
        if fault is Fault.CLEAN_EOF or fault is Fault.DROP_CONNECTION:
            conn.running = False
            await conn.aclose()
            self._connections.pop(conn.connection_id, None)
            return
        conn.arm(fault)

    def _note_execution(self, pending: PendingExecution) -> None:
        self.open_executions[pending.event_uuid] = pending
        self._executions.put_nowait(pending)

    def _remember_application(self, pending: PendingExecution) -> None:
        record = self.records.get(pending.channel_uuid)
        if record is None or pending.application == "":
            return
        record.application = pending.application
        record.application_data = pending.data

    async def _fanout_event(self, headers: Sequence[Header], frame: ESLFrame) -> None:
        for conn in list(self._connections.values()):
            if conn.authed and conn.running and conn.wants(tuple(headers)):
                await conn.send_event(frame)

    def _preempt(self, connection_id: str, frame: ESLFrame) -> None:
        self.connection(connection_id).preempt.append(frame)

    def _targets(self, connection_id: Optional[str]) -> List[Connection]:
        if connection_id is None:
            return list(self._connections.values())
        return [self.connection(connection_id)]

    def _single(self, connection_id: Optional[str]) -> Connection:
        if connection_id is not None:
            return self.connection(connection_id)
        if len(self._connections) != 1:
            raise RuntimeError(
                "fail() needs a connection_id when more than one peer is up"
            )
        return next(iter(self._connections.values()))

    def _next_id(self) -> str:
        self._seq += 1
        return "c%s" % self._seq

    def _make_connection(
        self,
        connection_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        outbound: bool,
        full: bool,
        session_uuid: Optional[str],
    ) -> Connection:
        return Connection(
            connection_id,
            reader,
            writer,
            self.journal,
            self.password,
            outbound=outbound,
            full=full,
            session_uuid=session_uuid,
            channels=self.channels,
            records=self.records,
            hangups=self.hangups,
            sessions=self.sessions,
            fanout=self._fanout_event,
            on_execution=self._note_execution,
        )

    async def _run(self, conn: Connection) -> None:
        try:
            await conn.serve()
        except asyncio.CancelledError:
            pass
        finally:
            self._connections.pop(conn.connection_id, None)

    async def _on_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        connection_id = self._next_id()
        conn = self._make_connection(
            connection_id,
            reader,
            writer,
            outbound=False,
            full=True,
            session_uuid=None,
        )
        self._connections[connection_id] = conn
        pending = self._pending_fault
        self._pending_fault = None
        if pending is Fault.STALL_READS:
            conn.stalled = True
            if self._arm_caught is not None:
                conn.stall_caught = self._arm_caught
            self._arm_caught = None
        elif pending is not None:
            conn.arm(pending)
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            await conn.serve()
        except asyncio.CancelledError:
            pass
        finally:
            self._connections.pop(connection_id, None)
            if task is not None:
                self._tasks.discard(task)
