"""Connection loss, command observation, and one-shot sends."""

import asyncio
import contextlib
from typing import AsyncIterator, Callable, Tuple
from unittest.mock import patch

import pytest

from genesis.exceptions import (
    AuthenticationError,
    ChannelError,
    ChannelNotFound,
    CommandStage,
    ConnectionError,
    ConnectionLost,
    UnconnectedError,
)
from genesis.protocol.base import Protocol
from genesis.protocol.metrics import (
    command_errors_counter,
    connection_errors_counter,
)
from genesis.protocol.parser import ESLEvent


class _Host(Protocol):
    """Protocol with a stand-in writer."""


class _Writer:
    """Records writes. Optional gate and drain failure, no real socket."""

    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self.hold_first_drain: asyncio.Event | None = None
        self.pause_at: int | None = None
        self.pause_gate: asyncio.Event | None = None
        self.fail_drain_at: int | None = None
        self._drains = 0
        self._closing = False

    def write(self, data: bytes) -> None:
        self.payloads.append(data)

    async def drain(self) -> None:
        self._drains += 1
        if self.hold_first_drain is not None and self._drains == 1:
            await self.hold_first_drain.wait()
        if (
            self.pause_gate is not None
            and self.pause_at is not None
            and self._drains == self.pause_at
        ):
            await self.pause_gate.wait()
        if self.fail_drain_at is not None and self._drains >= self.fail_drain_at:
            raise ConnectionResetError("reset")

    def is_closing(self) -> bool:
        return self._closing

    def close(self) -> None:
        self._closing = True


def _reply(text: str) -> bytes:
    return f"Content-Type: command/reply\nReply-Text: {text}\n\n".encode()


def _contains(writer: _Writer, snippet: str) -> bool:
    needle = snippet.encode()
    return any(needle in payload for payload in writer.payloads)


async def _yield_once() -> None:
    ready = asyncio.Event()
    asyncio.get_running_loop().call_soon(ready.set)
    await ready.wait()


async def _until(predicate: Callable[[], bool]) -> None:
    for _ in range(40):
        if predicate():
            return
        await _yield_once()
    raise AssertionError("condition not met")


async def _cleanup(proto: Protocol, writer: _Writer) -> None:
    if writer.hold_first_drain is not None:
        writer.hold_first_drain.set()
    if writer.pause_gate is not None:
        writer.pause_gate.set()
    tasks = [proto.producer, proto.consumer, *list(proto.handler_tasks)]
    for task in tasks:
        if task is not None and not task.done():
            task.cancel()
    for task in tasks:
        if task is None:
            continue
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await asyncio.wait_for(task, 1)


@pytest.fixture
async def link() -> AsyncIterator[Tuple[_Host, asyncio.StreamReader, _Writer]]:
    reader = asyncio.StreamReader()
    writer = _Writer()
    proto = _Host()
    proto.reader = reader
    proto.writer = writer  # type: ignore[assignment]
    await proto.start()
    try:
        yield proto, reader, writer
    finally:
        await _cleanup(proto, writer)


def test_connection_lost_and_channel_not_found_fit_existing_catches() -> None:
    """Existing connection and channel handlers keep catching the new errors."""
    lost = ConnectionLost(CommandStage.NOT_SENT)
    missing = ChannelNotFound("abc")
    assert isinstance(lost, ConnectionError)
    assert lost.stage is CommandStage.NOT_SENT
    assert isinstance(missing, ChannelError)
    assert missing.uuid == "abc"


async def test_err_reply_is_returned(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A delivered -ERR stays an ESLEvent."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api nope"))
    await _until(lambda: _contains(writer, "api nope"))
    reader.feed_data(_reply("-ERR no such command"))
    event = await asyncio.wait_for(pending, 1)
    assert isinstance(event, ESLEvent)
    assert event["Reply-Text"] == "-ERR no such command"


async def test_span_failure_writes_the_command_once(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """Tracing failure after a successful write must not send again."""
    proto, reader, writer = link

    class _Span:
        def __enter__(self) -> "_Span":
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
            raise RuntimeError("span close failed")

        def set_attribute(self, *args: object, **kwargs: object) -> None:
            return None

        def set_status(self, *args: object, **kwargs: object) -> None:
            return None

        def record_exception(self, *args: object, **kwargs: object) -> None:
            return None

    with patch(
        "genesis.protocol.base.tracer.start_as_current_span", return_value=_Span()
    ):
        pending = asyncio.create_task(proto.send("api status"))
        await _until(lambda: _contains(writer, "api status"))
        reader.feed_data(_reply("+OK"))
        event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert len(writer.payloads) == 1


async def test_concurrent_replies_stay_in_send_order(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """Two in-flight commands receive replies in write order."""
    proto, reader, writer = link
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))
    second = asyncio.create_task(proto.send("api beta"))
    await _until(lambda: _contains(writer, "api beta"))
    reader.feed_data(_reply("+OK alpha"))
    reader.feed_data(_reply("+OK beta"))
    assert (await asyncio.wait_for(first, 1))["Reply-Text"] == "+OK alpha"
    assert (await asyncio.wait_for(second, 1))["Reply-Text"] == "+OK beta"


async def test_cancel_after_write_does_not_deliver_that_reply_to_the_next_send(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A cancelled caller keeps its reply off the next caller."""
    proto, reader, writer = link
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))
    await _yield_once()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    proto.raise_if_lost(CommandStage.ACCEPTED)

    second = asyncio.create_task(proto.send("api beta"))
    await _until(lambda: _contains(writer, "api beta"))
    reader.feed_data(_reply("+OK alpha"))
    reader.feed_data(_reply("+OK beta"))
    event = await asyncio.wait_for(second, 1)
    assert event["Reply-Text"] == "+OK beta"


async def test_cancel_before_write_does_not_leave_a_tombstone(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """Cancellation that never reached write() does not consume a reply."""
    proto, reader, writer = link
    writer.hold_first_drain = asyncio.Event()
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))

    second = asyncio.create_task(proto.send("api beta"))
    await _yield_once()
    await _yield_once()
    assert not _contains(writer, "api beta")
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second

    writer.hold_first_drain.set()
    reader.feed_data(_reply("+OK alpha"))
    assert (await asyncio.wait_for(first, 1))["Reply-Text"] == "+OK alpha"

    third = asyncio.create_task(proto.send("api gamma"))
    await _until(lambda: _contains(writer, "api gamma"))
    reader.feed_data(_reply("+OK gamma"))
    assert (await asyncio.wait_for(third, 1))["Reply-Text"] == "+OK gamma"
    assert len([payload for payload in writer.payloads if b"api beta" in payload]) == 0


async def test_clean_eof_wakes_every_pending_send(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """Clean EOF fails every command that already reached write()."""
    proto, reader, writer = link
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))
    second = asyncio.create_task(proto.send("api beta"))
    await _until(lambda: _contains(writer, "api beta"))
    reader.feed_eof()
    for pending in (first, second):
        with pytest.raises(ConnectionLost) as caught:
            await asyncio.wait_for(pending, 1)
        assert caught.value.stage is CommandStage.UNCONFIRMED


async def test_truncated_body_wakes_pending_send(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A short body then EOF fails the pending command."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(b"Content-Type: api/response\nContent-Length: 20\n\nshort")
    reader.feed_eof()
    with pytest.raises(ConnectionLost) as caught:
        await asyncio.wait_for(pending, 1)
    assert caught.value.stage is CommandStage.UNCONFIRMED


async def test_disconnect_notice_wakes_pending_send_without_deadlock(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """text/disconnect-notice fails pending commands and stop() returns."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(b"Content-Type: text/disconnect-notice\n\n")
    with pytest.raises(ConnectionLost) as caught:
        await asyncio.wait_for(pending, 1)
    assert caught.value.stage is CommandStage.UNCONFIRMED
    assert proto.consumer is not None
    await asyncio.wait_for(proto.consumer, 1)


async def test_rude_rejection_wakes_pending_send(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """text/rude-rejection fails pending commands."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(b"Content-Type: text/rude-rejection\n\n")
    with pytest.raises(ConnectionLost) as caught:
        await asyncio.wait_for(pending, 1)
    assert caught.value.stage is CommandStage.UNCONFIRMED


async def test_linger_disconnect_keeps_the_command_wait(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A linger disposition does not fail the open command."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(
        b"Content-Type: text/disconnect-notice\nContent-Disposition: linger\n\n"
    )
    reader.feed_data(_reply("+OK"))
    event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert proto.is_connected is True


async def test_drain_error_is_unconfirmed_and_later_send_is_not_sent(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A drain error after write fails every pending waiter once."""
    proto, reader, writer = link
    writer.fail_drain_at = 2
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))
    second = asyncio.create_task(proto.send("api beta"))
    with pytest.raises(ConnectionLost) as beta:
        await asyncio.wait_for(second, 1)
    with pytest.raises(ConnectionLost) as alpha:
        await asyncio.wait_for(first, 1)
    assert alpha.value.stage is CommandStage.UNCONFIRMED
    assert beta.value.stage is CommandStage.UNCONFIRMED
    assert len(writer.payloads) == 2
    with pytest.raises(ConnectionLost) as later:
        await proto.send("api gamma")
    assert later.value.stage is CommandStage.NOT_SENT
    assert not _contains(writer, "api gamma")
    del reader


async def test_auth_wait_unblocks_on_eof(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """EOF before auth/request releases the auth wait and does not write."""
    proto, reader, writer = link
    waiting = asyncio.create_task(proto.authentication_event.wait())
    reader.feed_eof()
    await asyncio.wait_for(waiting, 1)
    with pytest.raises(ConnectionLost) as caught:
        await proto.send("auth secret")
    assert caught.value.stage is CommandStage.NOT_SENT
    assert writer.payloads == []


async def test_invalid_password_reply_before_close_raises_authentication_error(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A buffered auth rejection is delivered before the following close."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("auth secret"))
    await _until(lambda: _contains(writer, "auth secret"))
    reader.feed_data(_reply("-ERR invalid"))
    reader.feed_eof()
    response = await asyncio.wait_for(pending, 1)
    with pytest.raises(AuthenticationError, match="Invalid password"):
        if response["Reply-Text"] != "+OK accepted":
            raise AuthenticationError("Invalid password")


async def test_stop_from_handler_returns(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """stop() called from a handler task does not wait for that task."""
    proto, reader, _writer = link
    finished = asyncio.Event()

    async def on_heartbeat(event: ESLEvent) -> None:
        del event
        await proto.stop()
        finished.set()

    proto.on("HEARTBEAT", on_heartbeat)
    reader.feed_data(b"Content-Type: text/event-plain\nEvent-Name: HEARTBEAT\n\n")
    await asyncio.wait_for(finished.wait(), 1)


async def test_stop_is_idempotent_and_later_send_is_unconnected(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """stop() wakes an in-flight write and a second stop is a no-op."""
    proto, _reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    await proto.stop()
    with pytest.raises(ConnectionLost) as caught:
        await asyncio.wait_for(pending, 1)
    assert caught.value.stage is CommandStage.UNCONFIRMED
    await proto.stop()
    with pytest.raises(UnconnectedError):
        await proto.send("api again")


async def test_wait_lost_raises_caller_stage(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """Already-closed and later-closed waits raise the stage the caller passes."""
    proto, reader, _writer = link
    waiting = asyncio.create_task(proto.wait_lost(CommandStage.ACCEPTED))
    reader.feed_eof()
    with pytest.raises(ConnectionLost) as caught:
        await asyncio.wait_for(waiting, 1)
    assert caught.value.stage is CommandStage.ACCEPTED
    with pytest.raises(ConnectionLost) as immediate:
        proto.raise_if_lost(CommandStage.NOT_SENT)
    assert immediate.value.stage is CommandStage.NOT_SENT


async def test_api_response_is_the_command_result(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """api/response bodies still complete the matching send."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api eval alpha"))
    await _until(lambda: _contains(writer, "api eval alpha"))
    reader.feed_data(b"Content-Type: api/response\nContent-Length: 5\n\nhello")
    event = await asyncio.wait_for(pending, 1)
    assert event.body == "hello"


async def test_event_between_commands_is_not_a_reply(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A plain event does not satisfy a pending command."""
    proto, reader, writer = link
    seen = asyncio.Event()

    async def on_heartbeat(event: ESLEvent) -> None:
        del event
        seen.set()

    proto.on("HEARTBEAT", on_heartbeat)
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(b"Content-Type: text/event-plain\nEvent-Name: HEARTBEAT\n\n")
    await asyncio.wait_for(seen.wait(), 1)
    reader.feed_data(_reply("+OK"))
    assert (await asyncio.wait_for(pending, 1))["Reply-Text"] == "+OK"


async def test_peer_loss_records_low_cardinality_connection_error(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """EOF records a fixed error label and no identifier attributes."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    with patch("genesis.protocol.base.safe_add") as add:
        reader.feed_eof()
        with pytest.raises(ConnectionLost):
            await asyncio.wait_for(pending, 1)
    errors = [
        call.kwargs.get("attributes", {})
        for call in add.call_args_list
        if call.args and call.args[0] is connection_errors_counter
    ]
    assert errors
    assert errors[0]["error"] == "eof"
    for attributes in errors:
        assert "uuid" not in attributes
        for value in attributes.values():
            assert " " not in str(value)
    command_errors = [
        call.kwargs.get("attributes", {})
        for call in add.call_args_list
        if call.args and call.args[0] is command_errors_counter
    ]
    assert any(
        item.get("stage") == CommandStage.UNCONFIRMED.value for item in command_errors
    )


def _release(reader: asyncio.StreamReader, writer: _Writer, *frames: bytes) -> None:
    def _same_turn() -> None:
        for frame in frames:
            reader.feed_data(frame)
        if writer.hold_first_drain is not None:
            writer.hold_first_drain.set()
        if writer.pause_gate is not None:
            writer.pause_gate.set()

    asyncio.get_running_loop().call_soon(_same_turn)


async def test_ack_already_buffered_survives_drain_error(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A command/reply queued before drain fails is the result. One write."""
    proto, reader, writer = link
    writer.hold_first_drain = asyncio.Event()
    writer.fail_drain_at = 1
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    _release(reader, writer, _reply("+OK"))
    event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert len(writer.payloads) == 1
    with pytest.raises(ConnectionLost) as later:
        await proto.send("api next")
    assert later.value.stage is CommandStage.NOT_SENT
    assert not _contains(writer, "api next")


async def test_queued_acks_for_other_waiters_survive_drain_error(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """fail_pending does not drop replies already sitting in the event queue."""
    proto, reader, writer = link
    writer.pause_at = 2
    writer.pause_gate = asyncio.Event()
    writer.fail_drain_at = 2
    first = asyncio.create_task(proto.send("api alpha"))
    await _until(lambda: _contains(writer, "api alpha"))
    second = asyncio.create_task(proto.send("api beta"))
    await _until(lambda: _contains(writer, "api beta"))
    _release(reader, writer, _reply("+OK alpha"), _reply("+OK beta"))
    assert (await asyncio.wait_for(first, 1))["Reply-Text"] == "+OK alpha"
    assert (await asyncio.wait_for(second, 1))["Reply-Text"] == "+OK beta"
    assert len(writer.payloads) == 2
    with pytest.raises(ConnectionLost) as later:
        await proto.send("api gamma")
    assert later.value.stage is CommandStage.NOT_SENT
    assert not _contains(writer, "api gamma")


async def test_reply_and_eof_in_one_buffer_returns_ok(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """command/reply followed by EOF in the same buffer is still +OK."""
    proto, reader, writer = link
    pending = asyncio.create_task(proto.send("api status"))
    await _until(lambda: _contains(writer, "api status"))
    reader.feed_data(_reply("+OK"))
    reader.feed_eof()
    event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert len(writer.payloads) == 1


async def test_span_open_failure_still_delivers_the_reply(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """process_event span open cannot drop a parsed command/reply."""
    proto, reader, writer = link

    class _Closed:
        def __enter__(self) -> "_Closed":
            raise RuntimeError("span open failed")

        def __exit__(self, *args: object) -> bool:
            return False

    with patch(
        "genesis.protocol.base.tracer.start_as_current_span", return_value=_Closed()
    ):
        pending = asyncio.create_task(proto.send("api status"))
        await _until(lambda: _contains(writer, "api status"))
        reader.feed_data(_reply("+OK"))
        event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert len(writer.payloads) == 1


async def test_metrics_failure_is_not_retried_and_reply_is_delivered(
    link: Tuple[_Host, asyncio.StreamReader, _Writer],
) -> None:
    """A raising event metric runs once and does not drop the reply."""
    proto, reader, writer = link
    calls = {"n": 0}

    def boom(_event: ESLEvent) -> None:
        calls["n"] += 1
        raise RuntimeError("metrics")

    with patch("genesis.protocol.base.record_event_metrics", side_effect=boom):
        pending = asyncio.create_task(proto.send("api status"))
        await _until(lambda: _contains(writer, "api status"))
        reader.feed_data(_reply("+OK"))
        event = await asyncio.wait_for(pending, 1)
    assert event["Reply-Text"] == "+OK"
    assert calls["n"] == 1
    assert len(writer.payloads) == 1
