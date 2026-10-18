"""One ESL peer. Subscriptions and filters belong to this connection."""

import asyncio
import re
from typing import Awaitable, Callable, Dict, List, Optional, Sequence, Tuple
from uuid import uuid4

from tests.simulator.channels import ChannelRecord, render_dump
from tests.simulator.codec import MAX_CONTENT_LENGTH, ESLFrame, Header
from tests.simulator.faults import Fault, synthetic_payload
from tests.simulator.journal import Journal
from tests.simulator.messages import (
    api_response,
    auth_request,
    command_reply,
    connect_reply,
    disconnect_notice,
    encode_event,
    event_plain,
    rude_rejection,
)

_ORIGINATION = re.compile(r"origination_uuid=([0-9a-fA-F-]+)")
Fanout = Callable[[Sequence[Header], ESLFrame], Awaitable[None]]


class CommandRejected(Exception):
    """An inbound command declared a length this peer will not read."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PendingExecution:
    """One ``sendmsg`` execute recorded from the command, not from a later event.

    ``lock`` copies ``event-lock: true``. FreeSWITCH uses that flag to block
    the session's private event queue. This simulator stores the flag and
    does not hold later ``sendmsg`` commands, does not run the application,
    and does not emit ``CHANNEL_EXECUTE`` until the scenario calls
    ``start_execution`` and then ``complete_execution``. A timeout case
    leaves the record pending.
    """

    def __init__(
        self,
        connection_id: str,
        channel_uuid: str,
        event_uuid: str,
        application: str,
        data: str,
        lock: bool,
    ) -> None:
        self.connection_id = connection_id
        self.channel_uuid = channel_uuid
        self.event_uuid = event_uuid
        self.application = application
        self.data = data
        self.lock = lock


_FULL_ONLY = frozenset({"api", "bgapi", "event", "sendevent", "log"})
_MYEVENT_NAMES = frozenset(
    {
        "CHANNEL_ANSWER",
        "CHANNEL_APPLICATION",
        "CHANNEL_BRIDGE",
        "CHANNEL_CREATE",
        "CHANNEL_DATA",
        "CHANNEL_DESTROY",
        "CHANNEL_EXECUTE",
        "CHANNEL_EXECUTE_COMPLETE",
        "CHANNEL_HANGUP",
        "CHANNEL_HANGUP_COMPLETE",
        "CHANNEL_ORIGINATE",
        "CHANNEL_UUID",
        "CHANNEL_OUTGOING",
        "CHANNEL_PARK",
        "CHANNEL_PROGRESS",
        "CHANNEL_PROGRESS_MEDIA",
        "CHANNEL_STATE",
        "CHANNEL_UNBRIDGE",
        "CHANNEL_UNPARK",
        "DETECTED_SPEECH",
        "DTMF",
        "NOTALK",
        "TALK",
    }
)


class Connection:
    """Inbound listener session or outbound dialplan peer."""

    def __init__(
        self,
        connection_id: str,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        journal: Journal,
        password: str,
        *,
        outbound: bool = False,
        full: bool = True,
        session_uuid: Optional[str] = None,
        channels: Optional[Dict[str, str]] = None,
        records: Optional[Dict[str, ChannelRecord]] = None,
        hangups: Optional[List[Tuple[str, str]]] = None,
        sessions: Optional[Dict[str, str]] = None,
        fanout: Optional[Fanout] = None,
        on_execution: Optional[Callable[[PendingExecution], None]] = None,
    ) -> None:
        self.connection_id = connection_id
        self.reader = reader
        self.writer = writer
        self.journal = journal
        self.password = password
        self.outbound = outbound
        self.full = full or not outbound
        self.session_uuid = session_uuid
        self.channels = channels if channels is not None else {}
        self.records = records if records is not None else {}
        self.hangups = hangups if hangups is not None else []
        self.sessions = sessions if sessions is not None else {}
        if outbound and session_uuid:
            self.sessions[session_uuid] = connection_id
            _register_outbound_channel(self, session_uuid)
        self.authed = outbound
        self.running = True
        self.all_events = False
        self.event_names: set[str] = set()
        self.custom: set[str] = set()
        self.filters: List[Tuple[str, str]] = []
        self.preempt: List[ESLFrame] = []
        self.pending: List[PendingExecution] = []
        self.pending_by_channel: Dict[str, List[PendingExecution]] = {}
        self._fanout = fanout
        self._on_execution = on_execution
        self.armed: Optional[Fault] = None
        self._write_mode: Optional[str] = None
        self.stalled = False
        self.stall_caught = asyncio.Event()
        self._resume = asyncio.Event()
        self._buffer = bytearray()
        self._write_lock = asyncio.Lock()

    def arm(self, fault: Fault) -> None:
        self.armed = fault

    def wants(self, headers: Sequence[Header]) -> bool:
        fields = _header_map(headers)
        name = fields.get("event-name", "")
        subclass = fields.get("event-subclass")
        if not self._subscribed(name, subclass):
            return False
        return _filters_allow(self.filters, fields)

    async def serve(self) -> None:
        try:
            if not self.outbound:
                await self._send_raw(auth_request(), record=auth_request_frame())
            while self.running:
                chunk = await self.reader.read(65536)
                if not chunk:
                    break
                if self.stalled:
                    self.stall_caught.set()
                    await self._resume.wait()
                    continue
                self._buffer.extend(chunk)
                try:
                    commands = _drain_commands(self._buffer)
                except CommandRejected as exc:
                    await self._reply("-ERR %s" % exc.reason)
                    self.running = False
                    break
                for command in commands:
                    await self._handle(command)
                    if not self.running:
                        break
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError):
            return
        finally:
            self.running = False
            await self.aclose()

    async def aclose(self) -> None:
        self.running = False
        self.stalled = False
        if not self._resume.is_set():
            self._resume.set()
        writer = self.writer
        if not writer.is_closing():
            writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass

    async def send_event(self, frame: ESLFrame) -> None:
        await self._send_raw(encode_event(frame), record=frame)

    async def _handle(self, command: str) -> None:
        self.journal.record_command(self.connection_id, command)
        fault = self.armed
        self.armed = None
        if fault is Fault.DISCONNECT_BEFORE_REPLY or fault is Fault.DROP_CONNECTION:
            self.running = False
            return
        if fault is Fault.CLEAN_EOF:
            self.running = False
            return
        if fault is Fault.TRUNCATED_REPLY:
            self._write_mode = "truncate"
        elif fault is Fault.ACK_THEN_DISCONNECT:
            self._write_mode = "close_after"
        if fault is Fault.SHORT_BODY:
            await self._send_raw(synthetic_payload("short_body"))
            return
        if fault is Fault.BAD_CONTENT_LENGTH:
            await self._send_raw(synthetic_payload("bad_content_length"))
            return
        if fault is Fault.RUDE_REJECTION:
            await self._send_raw(rude_rejection())
            self.running = False
            return
        first, _headers = _split_command(command)
        verb = _verb(first)
        if verb == "exit" or first == "...":
            await self._exit()
            return
        if not self.authed:
            await self._unauthenticated(first, fault)
            return
        if self.outbound and not self.full and verb in _FULL_ONLY:
            await self._reply("-ERR command not found")
            return
        handler = _DISPATCH.get(verb)
        if handler is None:
            await self._reply("-ERR command not found")
            return
        try:
            await handler(self, first, command)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._reply("-ERR internal error")

    async def deliver(self, headers: Sequence[Header], frame: ESLFrame) -> None:
        """Give ``frame`` to every authed peer whose subscription and filters match."""
        if self._fanout is not None:
            await self._fanout(headers, frame)
            return
        if self.authed and self.wants(headers):
            await self.send_event(frame)

    async def _unauthenticated(self, first: str, fault: Optional[Fault]) -> None:
        if not first.lower().startswith("auth "):
            await self._reply("-ERR command not found")
            self.running = False
            return
        supplied = first[5:]
        reject = fault is Fault.BAD_PASSWORD or supplied != self.password
        if reject:
            await self._reply("-ERR invalid")
            await self._send_raw(disconnect_notice())
            self.running = False
            return
        self.authed = True
        await self._reply("+OK accepted")

    async def _exit(self) -> None:
        await self._reply("+OK bye")
        await self._send_raw(
            disconnect_notice(self.session_uuid if self.outbound else None)
        )
        self.running = False

    async def _reply(self, text: str, extra: Sequence[Header] = ()) -> None:
        headers: List[Header] = [("Reply-Text", text)]
        headers.extend(extra)
        await self._write_reply(command_reply(*headers))

    async def _write_reply(self, payload: bytes) -> None:
        frames = list(self.preempt)
        self.preempt = []
        mode = self._write_mode
        self._write_mode = None
        outgoing = payload
        decoded: Optional[ESLFrame] = _frame_from_bytes(payload)
        if mode == "truncate":
            outgoing = payload[:-1] if payload else b""
            decoded = None
        async with self._write_lock:
            for frame in frames:
                self.writer.write(encode_event(frame))
                self.journal.record_event(self.connection_id, frame)
            self.writer.write(outgoing)
            await self.writer.drain()
            if mode in ("truncate", "close_after"):
                self.running = False
                if not self.writer.is_closing():
                    self.writer.close()
            if decoded is not None:
                self.journal.record_event(self.connection_id, decoded)

    async def _send_raw(
        self, payload: bytes, record: Optional[ESLFrame] = None
    ) -> None:
        async with self._write_lock:
            self.writer.write(payload)
            await self.writer.drain()
        if record is not None:
            self.journal.record_event(self.connection_id, record)

    def _subscribed(self, name: str, subclass: Optional[str]) -> bool:
        if self.all_events:
            return True
        if name == "CUSTOM":
            return bool(subclass) and subclass in self.custom
        return name in self.event_names


def auth_request_frame() -> ESLFrame:
    return ESLFrame((("Content-Type", "auth/request"),), b"")


async def _on_event(conn: Connection, first: str, command: str) -> None:
    del command
    # "events plain ALL" skips the bytes before the first space, same as
    # mod_event_socket.c reading five characters of "event".
    body = first.split(" ", 1)[1] if " " in first else ""
    parts = body.split()
    if parts and parts[0].lower() in ("xml", "json"):
        await conn._reply("-ERR unsupported event format")
        return
    if parts and parts[0].lower() == "plain":
        parts = parts[1:]
    if not parts:
        await conn._reply("-ERR no keywords supplied")
        return
    custom = False
    count = 0
    for token in parts:
        upper = token.upper()
        if custom:
            conn.custom.add(token)
            count += 1
            continue
        if upper == "ALL":
            conn.all_events = True
            count += 1
        elif upper == "CUSTOM":
            custom = True
            conn.event_names.add("CUSTOM")
            count += 1
        else:
            conn.event_names.add(upper)
            count += 1
    if count == 0:
        await conn._reply("-ERR no keywords supplied")
        return
    await conn._reply("+OK event listener enabled plain")


async def _on_nixevent(conn: Connection, first: str, command: str) -> None:
    del command
    parts = first.split()[1:]
    if not parts:
        await conn._reply("-ERR no keywords supplied")
        return
    custom = False
    for token in parts:
        if custom:
            conn.custom.discard(token)
            continue
        upper = token.upper()
        if upper == "ALL":
            conn.all_events = False
            conn.event_names.clear()
            conn.custom.clear()
        elif upper == "CUSTOM":
            custom = True
            conn.event_names.discard("CUSTOM")
        else:
            conn.event_names.discard(upper)
            if upper == "ALL":
                conn.all_events = False
    await conn._reply("+OK events nixed")


async def _on_noevents(conn: Connection, first: str, command: str) -> None:
    del first, command
    if not conn.all_events and not conn.event_names and not conn.custom:
        await conn._reply("-ERR not listening for events")
        return
    conn.all_events = False
    conn.event_names.clear()
    conn.custom.clear()
    await conn._reply("+OK no longer listening for events")


async def _on_filter(conn: Connection, first: str, command: str) -> None:
    del command
    parts = first.split()
    if len(parts) < 3:
        await conn._reply("-ERR invalid syntax")
        return
    if parts[1].lower() == "delete":
        if len(parts) < 4 and parts[2].lower() != "all":
            await conn._reply("-ERR invalid syntax")
            return
        if parts[2].lower() == "all":
            conn.filters.clear()
            await conn._reply("+OK filter deleted. [all][]")
            return
        header, value = parts[2], parts[3]
        conn.filters = [
            item
            for item in conn.filters
            if not (item[0] == header and item[1] == value)
        ]
        await conn._reply("+OK filter deleted. [%s][%s]" % (header, value))
        return
    header = parts[1]
    if header.lower() == "add":
        if len(parts) < 4:
            await conn._reply("-ERR invalid syntax")
            return
        header, value = parts[2], parts[3]
    else:
        value = parts[2]
    conn.filters.append((header, value))
    await conn._reply("+OK filter added. [%s]=[%s]" % (header, value))


async def _on_api(conn: Connection, first: str, command: str) -> None:
    del command
    rest = first.split(" ", 2)
    name = rest[1] if len(rest) > 1 else ""
    argument = rest[2] if len(rest) > 2 else ""
    body = _api_body(conn, name, argument, first)
    await conn._write_reply(api_response(body))


async def _on_bgapi(conn: Connection, first: str, command: str) -> None:
    job = _job_uuid(command) or str(uuid4())
    payload = command_reply(
        ("Reply-Text", "+OK Job-UUID: %s" % job),
        ("Job-UUID", job),
    )
    await conn._write_reply(payload)
    api_name = first.split()[1] if len(first.split()) > 1 else ""
    result = _api_body(conn, api_name, "", first)
    headers: Tuple[Header, ...] = (
        ("Event-Name", "BACKGROUND_JOB"),
        ("Job-UUID", job),
        ("Job-Command", api_name),
    )
    await conn.deliver(headers, event_plain(headers, result))


async def _on_sendmsg(conn: Connection, first: str, command: str) -> None:
    """Reply from ``parse_command`` sendmsg in pinned mod_event_socket.c.

    An empty uuid is ``+OK`` only while this socket still controls a live
    session. Any other uuid must locate a channel. Otherwise the reply is
    ``-ERR invalid session id [<uuid>]`` and no execution is recorded.
    """
    asked = _sendmsg_uuid(first, command)
    if not _sendmsg_located(conn, asked):
        await conn._reply("-ERR invalid session id [%s]" % asked)
        return
    pending = _pending_execution(conn, first, command)
    if pending is not None:
        if asked:
            pending.channel_uuid = asked
        conn.pending.append(pending)
        channel_queue = conn.pending_by_channel.setdefault(pending.channel_uuid, [])
        channel_queue.append(pending)
        if conn._on_execution is not None:
            conn._on_execution(pending)
    await conn._reply("+OK")


async def _on_linger(conn: Connection, first: str, command: str) -> None:
    del command
    if conn.session_uuid is None and not conn.outbound:
        await conn._reply("-ERR not controlling a session")
        return
    tail = first[6:].strip()
    if tail:
        await conn._reply("+OK will linger %s seconds" % tail.split()[0])
        return
    await conn._reply("+OK will linger")


async def _on_myevents(conn: Connection, first: str, command: str) -> None:
    del first, command
    conn.event_names.update(_MYEVENT_NAMES)
    if conn.session_uuid:
        conn.filters.append(("Unique-ID", conn.session_uuid))
    await conn._reply("+OK Events Enabled")


async def _on_connect(conn: Connection, first: str, command: str) -> None:
    del first, command
    if not conn.outbound or conn.session_uuid is None:
        await conn._reply("-ERR not controlling a session")
        return
    control = "full" if conn.full else "single-channel"
    payload = connect_reply(
        (
            ("Event-Name", "CHANNEL_DATA"),
            ("Channel-State", "CS_EXECUTE"),
            ("Channel-Name", "loopback/pilot"),
            ("Unique-ID", conn.session_uuid),
            ("Channel-Unique-ID", conn.session_uuid),
            ("Call-Direction", "inbound"),
            ("Answer-State", "early"),
            ("Content-Type", "command/reply"),
            ("Reply-Text", "+OK\n"),
            ("Socket-Mode", "async"),
            ("Control", control),
        )
    )
    frame = ESLFrame(
        (
            ("Event-Name", "CHANNEL_DATA"),
            ("Content-Type", "command/reply"),
            ("Reply-Text", "%2BOK%0A"),
            ("Socket-Mode", "async"),
            ("Control", control),
            ("Unique-ID", conn.session_uuid),
            ("Channel-State", "CS_EXECUTE"),
        ),
        b"",
    )
    await conn._send_raw(payload, record=frame)


async def _on_sendevent(conn: Connection, first: str, command: str) -> None:
    event_uuid = str(uuid4())
    name = "CUSTOM"
    parts = first.split()
    if len(parts) > 1:
        name = parts[1]
    subclass = _header_from_command(command, "Event-Subclass")
    await conn._reply("+OK %s" % event_uuid)
    fields: List[Header] = [("Event-Name", name), ("Event-UUID", event_uuid)]
    if subclass:
        fields.insert(0, ("Event-Subclass", subclass))
    for line in command.splitlines()[1:]:
        key, sep, value = line.partition(":")
        if sep != ":" or key == "":
            continue
        if key.lower() in ("event-subclass", "event-name"):
            continue
        fields.append((key.strip(), value.lstrip(" ")))
    await conn.deliver(fields, _plain(fields))


def _plain(headers: Sequence[Header]) -> ESLFrame:
    return event_plain(headers)


def _api_body(conn: Connection, name: str, argument: str, first: str) -> bytes:
    lowered = name.lower()
    if lowered == "create_uuid":
        return (str(uuid4()) + "\n").encode("utf-8")
    if lowered == "originate":
        return _originate(conn, first)
    if lowered == "uuid_exists":
        return _uuid_exists(conn, argument)
    if lowered == "uuid_dump":
        return _uuid_dump(conn, argument)
    if lowered == "uuid_kill":
        return _uuid_kill(conn, argument)
    if lowered == "uuid_bridge":
        return _uuid_bridge(conn, argument)
    if lowered == "eval":
        return argument.encode("utf-8")
    if lowered == "status":
        return b"UP 0\n"
    return ("-ERR %s Command not found!\n" % (name or "api")).encode("utf-8")


def _originate(conn: Connection, first: str) -> bytes:
    match = _ORIGINATION.search(first)
    channel_uuid = match.group(1) if match else str(uuid4())
    dial = first
    brace = first.rfind("}")
    park = first.find(" &park")
    if brace != -1 and park != -1 and park > brace:
        dial = first[brace + 1 : park].strip()
    conn.channels[channel_uuid] = dial
    return ("+OK %s\n" % channel_uuid).encode("utf-8")


def _register_outbound_channel(conn: Connection, session_uuid: str) -> None:
    """A dialplan socket's session is a channel until ``uuid_kill`` drops it."""
    conn.channels.setdefault(session_uuid, "loopback/pilot")
    if session_uuid in conn.records:
        return
    conn.records[session_uuid] = ChannelRecord(
        session_uuid,
        name=conn.channels[session_uuid],
        state="CS_EXECUTE",
        call_state="ACTIVE",
        answer_state="early",
    )


def _sendmsg_uuid(first: str, command: str) -> str:
    parts = first.split()
    if len(parts) > 1:
        return parts[1]
    header = _header_from_command(command, "session-id")
    return header or ""


def _located(conn: Connection, channel_uuid: str) -> bool:
    if channel_uuid == "":
        return False
    if channel_uuid in conn.records or channel_uuid in conn.channels:
        return True
    return channel_uuid in conn.sessions


def _sendmsg_located(conn: Connection, asked: str) -> bool:
    if asked:
        return _located(conn, asked)
    controlled = conn.session_uuid or ""
    return _located(conn, controlled)


def _leg_known(conn: Connection, channel_uuid: str) -> bool:
    return _located(conn, channel_uuid)


def _uuid_bridge(conn: Connection, argument: str) -> bytes:
    """Reply from ``uuid_bridge_function`` in pinned mod_commands.c.

    Success writes ``+OK <other uuid>``. A missing leg writes
    ``-ERR Invalid uuid``. The third-uuid fallback and
    ``switch_ivr_uuid_bridge`` media (``CHANNEL_BRIDGE``) are not simulated.
    """
    parts = argument.split()
    if len(parts) < 2:
        return b"-USAGE: <uuid> <other_uuid>\n"
    left, right = parts[0], parts[1]
    if _leg_known(conn, left) and _leg_known(conn, right):
        return ("+OK %s\n" % right).encode("utf-8")
    return b"-ERR Invalid uuid\n"


def _uuid_dump(conn: Connection, argument: str) -> bytes:
    """Body from ``uuid_dump_function`` in pinned mod_commands.c.

    No argument is ``-USAGE``. An unknown uuid is ``-ERR No such channel!``.
    The default format, and ``txt``, percent-encodes header values. ``plain``
    wraps each value in brackets.
    """
    parts = argument.split()
    if not parts:
        return b"-USAGE: <uuid> [format]\n"
    record = _lookup(conn, parts[0])
    if record is None:
        return b"-ERR No such channel!\n"
    plain = len(parts) > 1 and parts[1].lower() == "plain"
    return render_dump(record, plain=plain)


def _uuid_exists(conn: Connection, argument: str) -> bytes:
    """Body from ``uuid_exists_function`` in pinned mod_commands.c.

    The body is ``true`` or ``false`` with no trailing newline. A missing
    argument is ``false``.
    """
    parts = argument.split()
    if not parts:
        return b"false"
    if _lookup(conn, parts[0]) is None:
        return b"false"
    return b"true"


def _drop_channel(conn: Connection, channel_uuid: str) -> None:
    conn.channels.pop(channel_uuid, None)
    conn.records.pop(channel_uuid, None)
    conn.sessions.pop(channel_uuid, None)


def _lookup(conn: Connection, channel_uuid: str) -> Optional[ChannelRecord]:
    """Return the row visible to this lookup, or None when it is absent."""
    if channel_uuid == "":
        return None
    record = conn.records.get(channel_uuid)
    if record is None and channel_uuid in conn.sessions:
        conn.channels.setdefault(channel_uuid, "loopback/pilot")
    if record is None and channel_uuid in conn.channels:
        answer_state = "early" if channel_uuid in conn.sessions else "answered"
        record = ChannelRecord(
            channel_uuid,
            name=conn.channels[channel_uuid],
            answer_state=answer_state,
        )
        conn.records[channel_uuid] = record
    if record is None:
        return None
    remaining = record.lookups_remaining
    if remaining is None:
        return record
    if remaining <= 0:
        _drop_channel(conn, channel_uuid)
        return None
    record.lookups_remaining = remaining - 1
    return record


def _uuid_kill(conn: Connection, argument: str) -> bytes:
    """Reply from ``kill_function`` (``uuid_kill``) in pinned mod_commands.c.

    A known leg returns ``+OK`` and is recorded. An unknown leg returns
    ``-ERR No such channel!``. Cause strings are stored as sent;
    ``switch_channel_str2cause`` is not applied.
    """
    parts = argument.split()
    if not parts:
        return b"-USAGE: <uuid> [cause]\n"
    channel_uuid = parts[0]
    cause = parts[1] if len(parts) > 1 else "NORMAL_CLEARING"
    if not _leg_known(conn, channel_uuid):
        return b"-ERR No such channel!\n"
    conn.hangups.append((channel_uuid, cause))
    _drop_channel(conn, channel_uuid)
    return b"+OK\n"


def _pending_execution(
    conn: Connection, first: str, command: str
) -> Optional[PendingExecution]:
    _ignored, headers = _split_command(command)
    fields = _header_map(headers)
    if fields.get("call-command", "").lower() != "execute":
        return None
    event_uuid = fields.get("event-uuid", "")
    if event_uuid == "":
        return None
    parts = first.split()
    channel_uuid = parts[1] if len(parts) > 1 else (conn.session_uuid or "")
    return PendingExecution(
        conn.connection_id,
        channel_uuid,
        event_uuid,
        fields.get("execute-app-name", ""),
        fields.get("execute-app-arg", ""),
        fields.get("event-lock", "").lower() == "true",
    )


def _job_uuid(command: str) -> Optional[str]:
    for line in command.splitlines():
        if line.lower().startswith("job-uuid:"):
            return line.split(":", 1)[1].strip()
    return None


def _header_from_command(command: str, name: str) -> Optional[str]:
    folded = name.lower()
    for line in command.splitlines():
        key, sep, value = line.partition(":")
        if sep == ":" and key.strip().lower() == folded:
            return value.lstrip(" ")
    return None


def _verb(first: str) -> str:
    word = first.split(" ", 1)[0].lower() if first else ""
    if word == "events":
        return "event"
    return word


def _split_command(command: str) -> Tuple[str, List[Header]]:
    lines = command.splitlines()
    first = lines[0] if lines else ""
    headers: List[Header] = []
    for line in lines[1:]:
        key, sep, value = line.partition(":")
        if sep == ":" and key != "":
            headers.append((key.strip(), value.lstrip(" ")))
    return first, headers


def _header_map(headers: Sequence[Header]) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for name, value in headers:
        fields.setdefault(name.lower(), value)
    return fields


def _filters_allow(filters: Sequence[Tuple[str, str]], fields: Dict[str, str]) -> bool:
    if not filters:
        return True
    send = False
    for name, stored in filters:
        actual = fields.get(name.lower())
        if actual is None:
            continue
        positive, needle = _filter_polarity(stored)
        if send and positive:
            continue
        if needle == "":
            continue
        if _filter_cmp(stored, actual, needle):
            if positive:
                send = True
            else:
                return False
    return send


def _filter_polarity(stored: str) -> Tuple[bool, str]:
    index = 0
    positive = True
    while index < len(stored):
        char = stored[index]
        if char == "+":
            positive = True
        elif char == "-":
            positive = False
        elif char != " ":
            break
        index += 1
    return positive, stored[index:]


def _filter_cmp(stored: str, actual: str, needle: str) -> bool:
    if stored.startswith("/"):
        try:
            return re.search(needle, actual) is not None
        except re.error:
            return False
    return actual.lower() == needle.lower()


def _drain_commands(buffer: bytearray) -> List[str]:
    commands: List[str] = []
    while True:
        command = _take_command(buffer)
        if command is None:
            return commands
        commands.append(command)


def _take_command(buffer: bytearray) -> Optional[str]:
    index = 0
    size = len(buffer)
    while index < size and buffer[index] in (10, 13):
        index += 1
    if index:
        del buffer[:index]
    split = _blank_line(buffer)
    if split is None:
        return None
    block, consumed = split
    length = _declared_length(block)
    if len(buffer) < consumed + length:
        return None
    body = bytes(buffer[consumed : consumed + length])
    del buffer[: consumed + length]
    text = block.decode("utf-8").replace("\r", "")
    if body:
        return text + "\n" + body.decode("utf-8")
    return text


def _declared_length(block: bytes) -> int:
    for raw_line in block.split(b"\n"):
        line = raw_line.decode("utf-8", "replace")
        if not line.lower().startswith("content-length:"):
            continue
        value = line.split(":", 1)[1].strip()
        if not value.isdigit():
            raise CommandRejected("invalid Content-Length")
        length = int(value)
        if length > MAX_CONTENT_LENGTH:
            raise CommandRejected("Content-Length exceeds %s" % MAX_CONTENT_LENGTH)
        return length
    return 0


def _blank_line(buffer: bytearray) -> Optional[Tuple[bytes, int]]:
    size = len(buffer)
    index = 0
    while index < size:
        if buffer[index] == 10:
            if index + 1 < size and buffer[index + 1] == 10:
                return bytes(buffer[:index]), index + 2
            if index + 2 < size and buffer[index + 1] == 13 and buffer[index + 2] == 10:
                return bytes(buffer[:index]), index + 3
        index += 1
    return None


def _frame_from_bytes(payload: bytes) -> Optional[ESLFrame]:
    from tests.simulator.codec import ESLDecoder

    decoder = ESLDecoder()
    frames = list(decoder.feed(payload))
    if not frames:
        return None
    return frames[0]


_DISPATCH = {
    "event": _on_event,
    "nixevent": _on_nixevent,
    "noevents": _on_noevents,
    "filter": _on_filter,
    "api": _on_api,
    "bgapi": _on_bgapi,
    "sendmsg": _on_sendmsg,
    "linger": _on_linger,
    "myevents": _on_myevents,
    "connect": _on_connect,
    "sendevent": _on_sendevent,
}
