"""Session sendmsg waits for its own execution, not the command ack."""

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, cast
from unittest.mock import patch

import pytest

from genesis import Outbound
from genesis.exceptions import (
    ChannelError,
    CommandStage,
    ConnectionLost,
    SessionGoneAway,
)
from genesis.protocol.parser import ESLEvent
from genesis.session import Session

from tests.simulator.server import Simulator

CHANNEL = "channel-0000-0000-0000-000000000001"
FIRST = "11111111-1111-1111-1111-111111111111"
SECOND = "22222222-2222-2222-2222-222222222222"


def _port(app: Outbound) -> int:
    sockets = app.server.sockets if app.server is not None else None
    assert sockets is not None
    return int(sockets[0].getsockname()[1])


async def test_hangup_complete_while_awaiting_execution_raises_session_gone_away(
    esl_server: Simulator,
) -> None:
    """CHANNEL_HANGUP_COMPLETE for this channel is not a successful execute."""
    finished = asyncio.Event()
    box: Dict[str, Any] = {}

    async def handler(session: Session) -> None:
        try:
            box["event"] = await session.sendmsg(
                "execute", "playback", "gone.wav", block=True
            )
        except SessionGoneAway as exc:
            box["error"] = exc
        finally:
            finished.set()

    app = Outbound(handler, "127.0.0.1", 0)
    await app.start(block=False)
    try:
        connection_id = await esl_server.connect_dialplan(
            "127.0.0.1", _port(app), full=True
        )
        pending = await esl_server.next_execution(1)
        await esl_server.emit(
            (
                ("Event-Name", "CHANNEL_HANGUP_COMPLETE"),
                ("Unique-ID", pending.channel_uuid),
                ("Hangup-Cause", "NORMAL_CLEARING"),
            ),
            connection_id=connection_id,
        )
        await asyncio.wait_for(finished.wait(), 1)
    finally:
        for task in list(app.tasks):
            task.cancel()
        await app.stop()

    assert isinstance(box.get("error"), SessionGoneAway)
    assert "event" not in box


async def test_late_complete_after_timeout_does_not_satisfy_the_next_command(
    esl_server: Simulator,
) -> None:
    """A timed-out execute keeps its complete event off the next execute."""
    first_done = asyncio.Event()
    saw_late = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()
    box: Dict[str, Any] = {}

    async def spy(event: ESLEvent) -> None:
        box.setdefault("seen", []).append(event.get("Application-UUID"))
        saw_late.set()

    async def handler(session: Session) -> None:
        if session.uuid:
            session.register_channel_handler(
                session.uuid, "CHANNEL_EXECUTE_COMPLETE", spy
            )
        try:
            await session.sendmsg(
                "execute", "playback", "first.wav", block=True, timeout=0.05
            )
        except asyncio.TimeoutError:
            box["timed_out"] = True
        finally:
            first_done.set()
        await release.wait()
        box["second"] = await session.sendmsg(
            "execute", "playback", "second.wav", block=True
        )
        finished.set()

    app = Outbound(handler, "127.0.0.1", 0)
    await app.start(block=False)
    try:
        await esl_server.connect_dialplan("127.0.0.1", _port(app), full=True)
        first = await esl_server.next_execution(1)
        await asyncio.wait_for(first_done.wait(), 1)
        await esl_server.complete_execution(first)
        await asyncio.wait_for(saw_late.wait(), 1)
        release.set()
        second = await esl_server.next_execution(1)
        await esl_server.complete_execution(second)
        await asyncio.wait_for(finished.wait(), 1)
    finally:
        for task in list(app.tasks):
            task.cancel()
        await app.stop()

    assert box.get("timed_out") is True
    assert isinstance(box.get("second"), ESLEvent)
    assert box["second"].get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert box["second"].get("Application-UUID") == second.event_uuid
    assert box["second"].get("Application-UUID") != first.event_uuid


class _Peer:
    """Minimal ESL peer that answers only what a test writes."""

    def __init__(self) -> None:
        self._commands: asyncio.Queue[str] = asyncio.Queue()
        self._writer: Optional[asyncio.StreamWriter] = None
        self._server: Optional[asyncio.AbstractServer] = None

    async def __aenter__(self) -> "_Peer":
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self

    async def __aexit__(self, *args: object) -> None:
        writer = self._writer
        if writer is not None:
            writer.close()
            await writer.wait_closed()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def port(self) -> int:
        assert self._server is not None and self._server.sockets
        return int(self._server.sockets[0].getsockname()[1])

    async def command(self) -> str:
        return await asyncio.wait_for(self._commands.get(), 1)

    async def reply(self, text: str) -> None:
        assert self._writer is not None
        self._writer.write(
            f"Content-Type: command/reply\nReply-Text: {text}\n\n".encode()
        )
        await self._writer.drain()

    async def close(self) -> None:
        assert self._writer is not None
        self._writer.close()
        await self._writer.wait_closed()

    async def hangup(self, channel_uuid: str) -> None:
        await self._event(
            (
                "Event-Name: CHANNEL_HANGUP_COMPLETE\n"
                f"Unique-ID: {channel_uuid}\n"
                "Hangup-Cause: NORMAL_CLEARING\n\n"
            )
        )

    async def execute_complete(self, application_uuid: str, channel_uuid: str) -> None:
        await self._event(
            (
                "Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                f"Application-UUID: {application_uuid}\n"
                f"Unique-ID: {channel_uuid}\n\n"
            )
        )

    async def _event(self, body: str) -> None:
        encoded = body.encode()
        frame = (
            f"Content-Type: text/event-plain\nContent-Length: {len(encoded)}\n\n".encode()
            + encoded
        )
        assert self._writer is not None
        self._writer.write(frame)
        await self._writer.drain()

    async def _serve(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writer = writer
        pending = b""
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            pending += chunk
            while b"\n\n" in pending:
                raw, pending = pending.split(b"\n\n", 1)
                await self._commands.put(raw.decode("utf-8"))


@asynccontextmanager
async def _session(
    peer: _Peer, channel_uuid: Optional[str] = CHANNEL
) -> AsyncIterator[Session]:
    reader, writer = await asyncio.open_connection("127.0.0.1", peer.port)
    session = Session(reader, writer)
    if channel_uuid is not None:
        session.context = {
            "Unique-ID": channel_uuid,
            "Channel-Unique-ID": channel_uuid,
        }
    await session.start()
    try:
        yield session
    finally:
        await session.stop()
        writer.close()
        await writer.wait_closed()


async def _until(predicate: Any) -> None:
    for _ in range(40):
        if predicate():
            return
        ready = asyncio.Event()
        asyncio.get_running_loop().call_soon(ready.set)
        await ready.wait()
    raise AssertionError("condition not met")


async def test_overlapping_executes_do_not_swap_completion_events() -> None:
    """Two in-flight executes each receive the complete event for their UUID."""
    async with _Peer() as peer:
        reader, writer = await asyncio.open_connection("127.0.0.1", peer.port)
        session = Session(reader, writer)
        session.context = {"Unique-ID": CHANNEL, "Channel-Unique-ID": CHANNEL}
        await session.start()
        try:
            first = asyncio.create_task(
                session.sendmsg(
                    "execute",
                    "playback",
                    "first.wav",
                    event_uuid=FIRST,
                    block=True,
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await _until(lambda: session.exchange.depth == 0)

            second = asyncio.create_task(
                session.sendmsg(
                    "execute",
                    "playback",
                    "second.wav",
                    event_uuid=SECOND,
                    block=True,
                )
            )
            await peer.command()
            await _until(lambda: session.exchange.depth == 1)
            second_seen = asyncio.Event()

            async def spy(event: ESLEvent) -> None:
                if event.get("Application-UUID") == SECOND:
                    second_seen.set()

            session.register_channel_handler(CHANNEL, "CHANNEL_EXECUTE_COMPLETE", spy)
            await peer.execute_complete(SECOND, CHANNEL)
            await asyncio.wait_for(second_seen.wait(), 1)
            await peer.execute_complete(FIRST, CHANNEL)
            first_event = await asyncio.wait_for(first, 1)
            await peer.reply("+OK")
            second_event = await asyncio.wait_for(second, 1)
        finally:
            await session.stop()
            writer.close()
            await writer.wait_closed()

    assert first_event.get("Application-UUID") == FIRST
    assert second_event.get("Application-UUID") == SECOND
    assert first_event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert second_event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"


async def test_err_reply_returns_without_waiting_for_completion() -> None:
    """A -ERR command reply is the sendmsg result and does not wait."""
    async with _Peer() as peer:
        reader, writer = await asyncio.open_connection("127.0.0.1", peer.port)
        session = Session(reader, writer)
        session.context = {"Unique-ID": CHANNEL, "Channel-Unique-ID": CHANNEL}
        await session.start()
        try:
            pending = asyncio.create_task(
                session.sendmsg("execute", "playback", "missing.wav", block=True)
            )
            await peer.command()
            await peer.reply("-ERR no such application")
            event = await asyncio.wait_for(pending, 1)
        finally:
            await session.stop()
            writer.close()
            await writer.wait_closed()

    assert event.get("Reply-Text") == "-ERR no such application"
    assert event.get("Event-Name") != "CHANNEL_EXECUTE_COMPLETE"


async def test_cancelling_one_execute_leaves_cancelled_error_and_the_next_command() -> (
    None
):
    """Caller cancellation is not connection loss and does not complete another execute."""
    async with _Peer() as peer:
        async with _session(peer) as session:
            first = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "first.wav", event_uuid=FIRST, block=True
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await _until(lambda: session.exchange.depth == 0)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first

            second = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "second.wav", event_uuid=SECOND, block=True
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await peer.execute_complete(FIRST, CHANNEL)
            await peer.execute_complete(SECOND, CHANNEL)
            event = await asyncio.wait_for(second, 1)

    assert first.cancelled()
    assert event.get("Application-UUID") == SECOND


async def test_loss_before_acknowledgement_keeps_the_protocol_stage() -> None:
    """An unacked send fails with the stage the protocol observed."""
    async with _Peer() as peer:
        async with _session(peer) as session:
            pending = asyncio.create_task(
                session.sendmsg("execute", "playback", "early.wav", block=True)
            )
            await peer.command()
            await peer.close()
            with pytest.raises(ConnectionLost) as caught:
                await asyncio.wait_for(pending, 1)
    assert caught.value.stage is CommandStage.UNCONFIRMED


async def test_loss_after_acknowledgement_is_accepted() -> None:
    """Once +OK was seen, connection loss interrupts completion as ACCEPTED."""
    async with _Peer() as peer:
        async with _session(peer) as session:
            pending = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "late.wav", event_uuid=FIRST, block=True
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await _until(lambda: session.exchange.depth == 0)
            await peer.close()
            with pytest.raises(ConnectionLost) as caught:
                await asyncio.wait_for(pending, 1)
            leftover = [
                task
                for task in asyncio.all_tasks()
                if not task.done() and "wait_lost" in repr(task.get_coro())
            ]
    assert caught.value.stage is CommandStage.ACCEPTED
    assert leftover == []


async def test_sendmsg_on_an_already_lost_connection_is_not_sent() -> None:
    """A sendmsg after the peer is gone does not write and reports NOT_SENT."""
    async with _Peer() as peer:
        async with _session(peer) as session:
            await _until(lambda: peer._writer is not None)
            await peer.close()
            waiter = asyncio.create_task(session.wait_lost(CommandStage.NOT_SENT))
            with pytest.raises(ConnectionLost):
                await asyncio.wait_for(waiter, 1)
            queued = peer._commands.qsize()
            with pytest.raises(ConnectionLost) as caught:
                await session.sendmsg("execute", "playback", "gone.wav", block=True)
    assert caught.value.stage is CommandStage.NOT_SENT
    assert peer._commands.qsize() == queued


async def test_hangup_on_another_channel_does_not_finish_the_execute() -> None:
    """Hangup for a different channel leaves this execute waiting."""
    seen = asyncio.Event()

    async def spy(event: ESLEvent) -> None:
        if event.get("Unique-ID") == "other-channel":
            seen.set()

    async with _Peer() as peer:
        async with _session(peer) as session:
            session.on("CHANNEL_HANGUP_COMPLETE", spy)
            pending = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "stay.wav", event_uuid=FIRST, block=True
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await _until(lambda: session.exchange.depth == 0)
            await peer.hangup("other-channel")
            await asyncio.wait_for(seen.wait(), 1)
            assert not pending.done()
            await peer.execute_complete(FIRST, CHANNEL)
            event = await asyncio.wait_for(pending, 1)

    assert event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert event.get("Application-UUID") == FIRST


async def test_stopping_while_waiting_reports_accepted_and_drops_the_loss_task() -> (
    None
):
    """session.stop() interrupts an acked execute and does not leave wait_lost running."""
    async with _Peer() as peer:
        reader, writer = await asyncio.open_connection("127.0.0.1", peer.port)
        session = Session(reader, writer)
        session.context = {"Unique-ID": CHANNEL, "Channel-Unique-ID": CHANNEL}
        await session.start()
        try:
            pending = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "stop.wav", event_uuid=FIRST, block=True
                )
            )
            await peer.command()
            await peer.reply("+OK")
            await _until(lambda: session.exchange.depth == 0)
            await session.stop()
            with pytest.raises(ConnectionLost) as caught:
                await asyncio.wait_for(pending, 1)
            leftover = [
                task
                for task in asyncio.all_tasks()
                if not task.done()
                and task.get_coro() is not None
                and "wait_lost" in repr(task.get_coro())
            ]
        finally:
            writer.close()
            await writer.wait_closed()

    assert caught.value.stage is CommandStage.ACCEPTED
    assert leftover == []


class _MemWriter:
    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        self.payloads.append(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True


def _plain(body: str) -> bytes:
    return f"Content-Type: text/event-plain\n{body}\n".encode()


async def _memory_session() -> tuple[Session, asyncio.StreamReader, _MemWriter]:
    reader = asyncio.StreamReader()
    writer = _MemWriter()
    session = Session(reader, cast(Any, writer))
    session.context = {"Unique-ID": CHANNEL, "Channel-Unique-ID": CHANNEL}
    await session.start()
    return session, reader, writer


async def test_completion_queued_with_eof_is_delivered() -> None:
    """CHANNEL_EXECUTE_COMPLETE already queued with EOF is not ACCEPTED."""
    session, reader, writer = await _memory_session()
    try:
        pending = asyncio.create_task(
            session.sendmsg(
                "execute", "playback", "late.wav", event_uuid=FIRST, block=True
            )
        )
        await _until(lambda: writer.payloads)
        reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
        await _until(lambda: session.exchange.depth == 0)
        reader.feed_data(
            _plain(
                f"Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                f"Application-UUID: {FIRST}\n"
                f"Unique-ID: {CHANNEL}\n"
            )
        )
        reader.feed_eof()
        event = await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert event.get("Application-UUID") == FIRST
    assert len(writer.payloads) == 1


async def test_ack_and_completion_queued_with_eof_keep_the_complete() -> None:
    """+OK and the complete in one buffer still return the complete event."""
    session, reader, writer = await _memory_session()
    try:
        pending = asyncio.create_task(
            session.sendmsg(
                "execute", "playback", "late.wav", event_uuid=FIRST, block=True
            )
        )
        await _until(lambda: writer.payloads)
        reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
        reader.feed_data(
            _plain(
                f"Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                f"Application-UUID: {FIRST}\n"
                f"Unique-ID: {CHANNEL}\n"
            )
        )
        reader.feed_eof()
        event = await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert event.get("Application-UUID") == FIRST
    assert event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert len(writer.payloads) == 1


async def test_hangup_queued_with_eof_is_session_gone_away() -> None:
    """CHANNEL_HANGUP_COMPLETE queued with EOF is not ConnectionLost(ACCEPTED)."""
    session, reader, writer = await _memory_session()
    try:
        pending = asyncio.create_task(
            session.sendmsg(
                "execute", "playback", "gone.wav", event_uuid=FIRST, block=True
            )
        )
        await _until(lambda: writer.payloads)
        reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
        await _until(lambda: session.exchange.depth == 0)
        reader.feed_data(
            _plain(
                "Event-Name: CHANNEL_HANGUP_COMPLETE\n"
                f"Unique-ID: {CHANNEL}\n"
                "Hangup-Cause: NORMAL_CLEARING\n"
            )
        )
        reader.feed_eof()
        with pytest.raises(SessionGoneAway):
            await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert len(writer.payloads) == 1


async def test_slow_handler_does_not_block_queued_completion() -> None:
    """A user handler that awaits is cancelled. The completion is still returned."""
    session, reader, writer = await _memory_session()
    started = asyncio.Event()
    gate = asyncio.Event()

    async def slow(event: ESLEvent) -> None:
        del event
        started.set()
        await gate.wait()

    session.register_channel_handler(CHANNEL, "CHANNEL_EXECUTE_COMPLETE", slow)
    try:
        pending = asyncio.create_task(
            session.sendmsg(
                "execute", "playback", "late.wav", event_uuid=FIRST, block=True
            )
        )
        await _until(lambda: writer.payloads)
        reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
        await _until(lambda: session.exchange.depth == 0)
        reader.feed_data(
            _plain(
                f"Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                f"Application-UUID: {FIRST}\n"
                f"Unique-ID: {CHANNEL}\n"
            )
        )
        reader.feed_eof()
        event = await asyncio.wait_for(pending, 1)
        await asyncio.wait_for(started.wait(), 1)
    finally:
        gate.set()
        await session.stop()
    assert event.get("Application-UUID") == FIRST


async def test_lifecycle_span_exit_still_dispatches_completion() -> None:
    """A lifecycle span __exit__ does not drop CHANNEL_EXECUTE_COMPLETE."""
    session, reader, writer = await _memory_session()

    class _ExitBoom:
        def __enter__(self) -> "_ExitBoom":
            return self

        def __exit__(self, *args: object) -> bool:
            raise RuntimeError("span close failed")

        def add_event(self, *args: object, **kwargs: object) -> None:
            return None

        def set_attribute(self, *args: object, **kwargs: object) -> None:
            return None

        def end(self) -> None:
            return None

    try:
        with patch(
            "genesis.protocol.lifecycle.tracer.start_as_current_span",
            return_value=_ExitBoom(),
        ):
            pending = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "late.wav", event_uuid=FIRST, block=True
                )
            )
            await _until(lambda: writer.payloads)
            reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
            await _until(lambda: session.exchange.depth == 0)
            reader.feed_data(
                _plain(
                    f"Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                    f"Application-UUID: {FIRST}\n"
                    f"Unique-ID: {CHANNEL}\n"
                )
            )
            event = await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert event.get("Application-UUID") == FIRST
    assert len(writer.payloads) == 1


async def test_session_metric_failure_returns_the_completion() -> None:
    """A raising session counter does not replace the completion event."""
    session, reader, writer = await _memory_session()
    try:
        with patch(
            "genesis.session.session_commands_counter.add",
            side_effect=RuntimeError("counter"),
        ) as added:
            pending = asyncio.create_task(
                session.sendmsg(
                    "execute", "playback", "late.wav", event_uuid=FIRST, block=True
                )
            )
            await _until(lambda: writer.payloads)
            reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
            await _until(lambda: session.exchange.depth == 0)
            reader.feed_data(
                _plain(
                    f"Event-Name: CHANNEL_EXECUTE_COMPLETE\n"
                    f"Application-UUID: {FIRST}\n"
                    f"Unique-ID: {CHANNEL}\n"
                )
            )
            event = await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert event.get("Application-UUID") == FIRST
    assert len(writer.payloads) == 1
    assert added.call_count == 1


async def test_session_span_exit_returns_the_ack() -> None:
    """session.sendmsg span close cannot replace a delivered +OK."""
    session, reader, writer = await _memory_session()

    class _ExitBoom:
        def __enter__(self) -> "_ExitBoom":
            return self

        def __exit__(self, *args: object) -> bool:
            raise RuntimeError("span close failed")

        def set_attribute(self, *args: object, **kwargs: object) -> None:
            return None

    try:
        with patch(
            "genesis.protocol.metrics.tracer.start_as_current_span",
            return_value=_ExitBoom(),
        ):
            pending = asyncio.create_task(
                session.sendmsg("execute", "playback", "file.wav", block=False)
            )
            await _until(lambda: writer.payloads)
            reader.feed_data(b"Content-Type: command/reply\nReply-Text: +OK\n\n")
            event = await asyncio.wait_for(pending, 1)
    finally:
        await session.stop()
    assert event["Reply-Text"] == "+OK"
    assert len(writer.payloads) == 1


async def test_sendmsg_after_local_stop_is_not_sent_for_both_block_modes() -> None:
    """stop() uses ConnectionLost(NOT_SENT) for block and non-block sendmsg."""
    session, _reader, writer = await _memory_session()
    await session.stop()
    with pytest.raises(ConnectionLost) as blocked:
        await session.sendmsg("execute", "playback", "gone.wav", block=True)
    with pytest.raises(ConnectionLost) as plain:
        await session.sendmsg("execute", "playback", "gone.wav", block=False)
    assert blocked.value.stage is CommandStage.NOT_SENT
    assert plain.value.stage is CommandStage.NOT_SENT
    assert writer.payloads == []


async def test_blocking_sendmsg_refuses_a_negative_completion_filter() -> None:
    """A negative filter that hides completion is not deleted and is not waited on."""
    reader = asyncio.StreamReader()
    writer = _MemWriter()
    session = Session(reader, cast(Any, writer))
    session.context = {"Unique-ID": CHANNEL, "Channel-Unique-ID": CHANNEL}
    session.subscriptions.observe(
        "filter Unique-ID -%s" % CHANNEL,
        ESLEvent({"Content-Type": "command/reply", "Reply-Text": "+OK"}),
    )
    with pytest.raises(ChannelError, match="CHANNEL_EXECUTE_COMPLETE"):
        await session.sendmsg("execute", "playback", "hidden.wav", block=True)
    assert writer.payloads == []
    assert ("Unique-ID", "-%s" % CHANNEL) in session.subscriptions.filters
