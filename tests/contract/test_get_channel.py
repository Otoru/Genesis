"""Inbound.get_channel and inbound channel execution against the simulator."""

import asyncio
from typing import Any, List, Optional, Tuple

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis import Channel, Inbound
from genesis.exceptions import (
    ChannelError,
    ChannelNotFound,
    CommandStage,
    ConnectionLost,
    SessionGoneAway,
)
from genesis.protocol.metrics import channel_operations_counter
from genesis.protocol.parser import ESLEvent
from genesis.types import ChannelState

from tests.simulator.faults import Fault
from tests.simulator.server import Simulator

PRESENT = "3814d229-50d9-440e-b91d-8d0801ff615d"
OTHER = "dc297fe0-7761-4226-b7cb-19ae8ec93968"
ABSENT = "61e6cf12-2e33-4491-812b-f5890c68ae50"

HeaderSet = Tuple[Tuple[str, str], ...]


def _lines(server: Simulator) -> Tuple[str, ...]:
    return tuple(item.text for item in server.journal.commands())


def _connection_id(server: Simulator) -> str:
    assert server.connection_ids
    return server.connection_ids[-1]


async def _until(predicate: Any) -> None:
    for _ in range(40):
        if predicate():
            return
        ready = asyncio.Event()
        asyncio.get_running_loop().call_soon(ready.set)
        await ready.wait()
    raise AssertionError("condition not met")


def _state(channel_uuid: str, state: str) -> HeaderSet:
    return (
        ("Event-Name", "CHANNEL_STATE"),
        ("Unique-ID", channel_uuid),
        ("Channel-State", state),
    )


class _MetricTap:
    def __init__(self) -> None:
        self.labels: List[dict[str, str]] = []
        self._real = channel_operations_counter.add

    def add(self, *args: object, **kwargs: object) -> None:
        attributes = kwargs.get("attributes")
        if isinstance(attributes, dict):
            self.labels.append(
                {str(key): str(value) for key, value in attributes.items()}
            )
        self._real(*args, **kwargs)

    def get_channel_labels(self) -> List[dict[str, str]]:
        return [item for item in self.labels if item.get("operation") == "get_channel"]


def _spans(exporter: InMemorySpanExporter, name: str) -> list[Any]:
    return [span for span in exporter.get_finished_spans() if span.name == name]


async def test_get_channel_reads_the_url_encoded_dump(esl_server: Simulator) -> None:
    """Default uuid_dump is the snapshot. Bracketed plain values are not used."""
    esl_server.seed_channel(
        PRESENT,
        name="loopback/9900-a",
        state="CS_EXECUTE",
        call_state="ACTIVE",
        answer_state="answered",
        application="park",
        variables={"variable_research_note": "café test"},
    )
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
    commands = _lines(esl_server)
    assert channel.uuid == PRESENT
    assert channel.state == ChannelState.EXECUTE
    assert channel.dial_path == "loopback/9900-a"
    assert channel.context["Channel-State"] == "CS_EXECUTE"
    assert channel.context["Channel-Call-State"] == "ACTIVE"
    assert channel.context["Answer-State"] == "answered"
    assert channel.context["Channel-Name"] == "loopback/9900-a"
    assert channel.context["variable_current_application"] == "park"
    assert channel.context["variable_research_note"] == "café test"
    assert "[" not in str(channel.context["Channel-State"])
    assert "api uuid_exists %s" % PRESENT in commands
    assert "api uuid_dump %s" % PRESENT in commands
    assert "api uuid_dump %s plain" % PRESENT not in commands
    assert not any(item.startswith("sendmsg") for item in commands)
    assert esl_server.open_executions == {}
    assert "myevents" not in commands


async def test_absent_uuid_raises_channel_not_found(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        with pytest.raises(ChannelNotFound) as caught:
            await client.get_channel(ABSENT)
    assert caught.value.uuid == ABSENT


async def test_channel_vanishes_between_exists_and_dump(esl_server: Simulator) -> None:
    """lookups=1 lets uuid_exists succeed and uuid_dump report the channel gone."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    esl_server.disappear_after(PRESENT, 1)
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        with pytest.raises(ChannelNotFound) as caught:
            await client.get_channel(PRESENT)
    assert caught.value.uuid == PRESENT
    commands = _lines(esl_server)
    assert "api uuid_exists %s" % PRESENT in commands
    assert "api uuid_dump %s" % PRESENT in commands


async def test_buffered_state_does_not_overwrite_the_snapshot(
    esl_server: Simulator,
) -> None:
    """A state event written before the dump reply is older than the snapshot."""
    esl_server.seed_channel(
        PRESENT,
        name="loopback/9900-a",
        state="CS_EXECUTE",
        call_state="ACTIVE",
        answer_state="answered",
    )
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("event plain ALL")
        esl_server.scenario.before_reply(
            _connection_id(esl_server),
            _state(PRESENT, "CS_ROUTING"),
        )
        channel = await client.get_channel(PRESENT)
    assert channel.state == ChannelState.EXECUTE
    assert channel.context.get("Channel-State") == "CS_EXECUTE"


async def test_later_state_reaches_the_channel_and_the_user_observer(
    esl_server: Simulator,
) -> None:
    """Channel registry routing must not swallow the caller's CHANNEL_STATE handler."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    user_saw = asyncio.Event()
    applied = asyncio.Event()

    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:

        def user(event: ESLEvent) -> None:
            if (
                event.get("Unique-ID") == PRESENT
                and event.get("Channel-State") == "CS_PARK"
            ):
                user_saw.set()

        client.on("CHANNEL_STATE", user)
        original = client.on

        def on(key: str, handler: Any) -> None:
            if key != "CHANNEL_STATE":
                original(key, handler)
                return

            def wrapped(event: ESLEvent) -> None:
                handler(event)
                if (
                    event.get("Unique-ID") == PRESENT
                    and event.get("Channel-State") == "CS_PARK"
                ):
                    applied.set()

            original(key, wrapped)

        client.on = on  # type: ignore[method-assign]
        channel = await client.get_channel(PRESENT)
        await esl_server.emit(_state(PRESENT, "CS_PARK"))
        await asyncio.wait_for(user_saw.wait(), 1)
        await asyncio.wait_for(applied.wait(), 1)
    assert channel.state == ChannelState.PARK


async def test_repeated_get_channel_returns_independent_objects(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("event plain ALL")
        first = await client.get_channel(PRESENT)
        second = await client.get_channel(PRESENT)
        first.context["marker"] = "first"
    assert first is not second
    assert first.uuid == second.uuid == PRESENT
    assert first.context is not second.context
    assert "marker" not in second.context
    event_commands = [item for item in _lines(esl_server) if item.startswith("event")]
    assert event_commands == ["event plain ALL"]


async def test_two_connections_observe_the_same_channel(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as left:
        async with Inbound(
            esl_server.host, esl_server.port, esl_server.password
        ) as right:
            first = await left.get_channel(PRESENT)
            second = await right.get_channel(PRESENT)
    assert first is not second
    assert first.context["Channel-Name"] == "loopback/9900-a"
    assert second.context["Channel-Name"] == "loopback/9900-a"


async def test_failed_lookup_drops_its_handlers_and_subscription(
    esl_server: Simulator,
) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        before = list(client.handlers.get("CHANNEL_STATE", []))
        processors = len(client.event_processors)
        with pytest.raises(ChannelNotFound):
            await client.get_channel(ABSENT)
        after = list(client.handlers.get("CHANNEL_STATE", []))
        assert len(client.event_processors) == processors
        beats = asyncio.Event()
        client.on("HEARTBEAT", lambda _event: beats.set())
        await client.send("event plain HEARTBEAT")
        await esl_server.emit((("Event-Name", "HEARTBEAT"),))
        await asyncio.wait_for(beats.wait(), 1)
    assert after == before
    commands = _lines(esl_server)
    assert any(item.startswith("nixevent ") for item in commands)
    assert "noevents" not in commands
    assert not any(item.startswith("filter delete") for item in commands)


async def test_all_subscription_is_left_intact(esl_server: Simulator) -> None:
    """An unfiltered ALL connection is not narrowed with Unique-ID or noevents."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        beats = asyncio.Event()
        client.on("HEARTBEAT", lambda _event: beats.set())
        await client.send("event plain ALL")
        await client.get_channel(PRESENT)
        await esl_server.emit((("Event-Name", "HEARTBEAT"),))
        await asyncio.wait_for(beats.wait(), 1)
    commands = _lines(esl_server)
    assert [item for item in commands if item.startswith("event")] == [
        "event plain ALL"
    ]
    assert not any(item.startswith("filter ") for item in commands)
    assert "myevents" not in commands
    assert "noevents" not in commands
    assert not any(item.startswith("nixevent") for item in commands)


async def test_positive_filters_gain_an_or_match_for_this_uuid(
    esl_server: Simulator,
) -> None:
    """A Unique-ID filter ORs with Event-Name HEARTBEAT. The heartbeat filter stays."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        beats = asyncio.Event()
        parked = asyncio.Event()
        applied = asyncio.Event()
        client.on("HEARTBEAT", lambda _event: beats.set())
        client.on(
            "CHANNEL_STATE",
            lambda event: (
                parked.set() if event.get("Channel-State") == "CS_PARK" else None
            ),
        )
        original = client.on

        def on(key: str, handler: Any) -> None:
            if key != "CHANNEL_STATE":
                original(key, handler)
                return

            def wrapped(event: ESLEvent) -> None:
                handler(event)
                if event.get("Channel-State") == "CS_PARK":
                    applied.set()

            original(key, wrapped)

        client.on = on  # type: ignore[method-assign]
        await client.send("event plain ALL")
        await client.send("filter Event-Name HEARTBEAT")
        channel = await client.get_channel(PRESENT)
        await esl_server.emit((("Event-Name", "HEARTBEAT"),))
        await asyncio.wait_for(beats.wait(), 1)
        await esl_server.emit(_state(PRESENT, "CS_PARK"))
        await asyncio.wait_for(parked.wait(), 1)
        await asyncio.wait_for(applied.wait(), 1)
    assert channel.state == ChannelState.PARK
    commands = _lines(esl_server)
    assert "filter Event-Name HEARTBEAT" in commands
    assert "filter Unique-ID %s" % PRESENT in commands
    assert not any(item.startswith("filter delete") for item in commands)


async def test_negative_filter_is_not_deleted(esl_server: Simulator) -> None:
    """A negative Unique-ID veto is someone else's config. The snapshot still returns."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("event plain ALL")
        await client.send("filter Unique-ID -%s" % PRESENT)
        channel = await client.get_channel(PRESENT)
    commands = _lines(esl_server)
    assert channel.state == ChannelState.EXECUTE
    assert not any(item.startswith("filter delete") for item in commands)
    assert "filter Unique-ID %s" % PRESENT not in commands


async def test_myevents_is_not_sent_or_cleared(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("myevents")
        channel = await client.get_channel(PRESENT)
    assert channel.uuid == PRESENT
    commands = _lines(esl_server)
    assert "myevents" in commands
    assert commands.count("myevents") == 1
    assert not any(item.startswith("event ") for item in commands)
    assert "noevents" not in commands
    assert not any(item.startswith("filter ") for item in commands)


async def test_invalid_uuid_never_reaches_the_wire(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        with pytest.raises(ChannelError) as caught:
            await client.get_channel("%s\napi status" % PRESENT)
        assert not isinstance(caught.value, ChannelNotFound)
        with pytest.raises(ChannelError):
            await client.get_channel("not-a-uuid")
    assert all("api status" not in item for item in _lines(esl_server))


async def test_disconnect_before_reply_is_not_channel_not_found(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await esl_server.fail(Fault.DISCONNECT_BEFORE_REPLY, _connection_id(esl_server))
        with pytest.raises(ConnectionLost) as caught:
            await client.get_channel(PRESENT)
    assert not isinstance(caught.value, ChannelNotFound)
    assert caught.value.stage is CommandStage.UNCONFIRMED


async def test_get_channel_on_a_lost_connection_is_not_sent(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await esl_server.fail(Fault.CLEAN_EOF, _connection_id(esl_server))
        await asyncio.wait_for(client._closed.wait(), 1)
        with pytest.raises(ConnectionLost) as caught:
            await client.get_channel(PRESENT)
    assert caught.value.stage is CommandStage.NOT_SENT


async def test_destroy_releases_the_subscription_we_added(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        wait = esl_server.journal.register_command_wait(
            lambda command: command.text.startswith("nixevent ")
        )
        channel = await client.get_channel(PRESENT)
        await esl_server.emit(_state(PRESENT, "CS_DESTROY"))
        await asyncio.wait_for(wait.wait(1), 1)
    assert channel.state == ChannelState.DESTROY


async def test_blocking_playback_waits_for_its_application_uuid(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        started = asyncio.Event()

        def on_execute(event: ESLEvent) -> None:
            if event.get("Event-Name") == "CHANNEL_EXECUTE":
                started.set()

        client.on("CHANNEL_EXECUTE", on_execute)
        task = asyncio.create_task(channel.playback("file.wav", block=True, timeout=2))
        pending = await esl_server.next_execution()
        await _until(lambda: client.exchange.depth == 0)
        assert not task.done()
        await esl_server.start_execution(pending)
        await asyncio.wait_for(started.wait(), 1)
        assert not task.done()
        await esl_server.complete_execution(pending)
        event = await asyncio.wait_for(task, 1)
    assert event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert event.get("Application-UUID") == pending.event_uuid
    command = next(item for item in _lines(esl_server) if item.startswith("sendmsg "))
    assert command.startswith("sendmsg %s\n" % PRESENT)
    assert "call-command: execute\n" in command
    assert "execute-app-name: playback\n" in command
    assert "execute-app-arg: file.wav\n" in command
    assert "Event-UUID: %s" % pending.event_uuid in command
    assert not any("uuid_execute" in item for item in _lines(esl_server))


async def test_nonblocking_playback_returns_the_ack(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        event = await asyncio.wait_for(
            channel.playback("file.wav", block=False),
            1,
        )
    assert event.get("Reply-Text") == "+OK"
    assert event.get("Event-Name") != "CHANNEL_EXECUTE_COMPLETE"


async def test_playback_timeout_does_not_complete_the_next_execute(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        with pytest.raises(asyncio.TimeoutError):
            task = asyncio.create_task(
                channel.playback("first.wav", block=True, timeout=0.05)
            )
            first = await esl_server.next_execution()
            await task
        await esl_server.complete_execution(first)
        second_task = asyncio.create_task(
            channel.playback("second.wav", block=True, timeout=2)
        )
        second = await esl_server.next_execution()
        await esl_server.complete_execution(second)
        event = await asyncio.wait_for(second_task, 1)
    assert event.get("Application-UUID") == second.event_uuid
    assert event.get("Application-UUID") != first.event_uuid


async def test_hangup_while_playback_blocks_raises_session_gone_away(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        task = asyncio.create_task(channel.playback("gone.wav", block=True, timeout=2))
        await esl_server.next_execution()
        await _until(lambda: client.exchange.depth == 0)
        await esl_server.emit(
            (
                ("Event-Name", "CHANNEL_HANGUP_COMPLETE"),
                ("Unique-ID", PRESENT),
                ("Hangup-Cause", "NORMAL_CLEARING"),
            )
        )
        with pytest.raises(SessionGoneAway):
            await asyncio.wait_for(task, 1)


async def test_other_channel_hangup_does_not_finish_playback(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    esl_server.seed_channel(OTHER, name="loopback/9900-b", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        other_hung_up = asyncio.Event()

        def spy(event: ESLEvent) -> None:
            if event.get("Unique-ID") == OTHER:
                other_hung_up.set()

        client.on("CHANNEL_HANGUP_COMPLETE", spy)
        task = asyncio.create_task(channel.playback("stay.wav", block=True, timeout=2))
        pending = await esl_server.next_execution()
        await _until(lambda: client.exchange.depth == 0)
        await esl_server.emit(
            (
                ("Event-Name", "CHANNEL_HANGUP_COMPLETE"),
                ("Unique-ID", OTHER),
            )
        )
        await asyncio.wait_for(other_hung_up.wait(), 1)
        assert not task.done()
        await esl_server.complete_execution(pending)
        event = await asyncio.wait_for(task, 1)
    assert event.get("Application-UUID") == pending.event_uuid


async def test_cancelling_playback_drops_the_completion_wait(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        task = asyncio.create_task(channel.playback("stop.wav", block=True, timeout=2))
        pending = await esl_server.next_execution()
        await _until(lambda: client.exchange.depth == 0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _until(
            lambda: not any(
                not item.done() and "wait_lost" in repr(item.get_coro())
                for item in asyncio.all_tasks()
            )
        )
        await esl_server.complete_execution(pending)
        follow = asyncio.create_task(
            channel.playback("next.wav", block=True, timeout=2)
        )
        nxt = await esl_server.next_execution()
        await esl_server.complete_execution(nxt)
        event = await asyncio.wait_for(follow, 1)
    assert event.get("Application-UUID") == nxt.event_uuid
    assert event.get("Application-UUID") != pending.event_uuid


async def test_loss_after_playback_ack_is_accepted(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        task = asyncio.create_task(channel.playback("late.wav", block=True, timeout=2))
        await esl_server.next_execution()
        await _until(lambda: client.exchange.depth == 0)
        await esl_server.fail(Fault.CLEAN_EOF, _connection_id(esl_server))
        with pytest.raises(ConnectionLost) as caught:
            await asyncio.wait_for(task, 1)
        leftover = [
            item
            for item in asyncio.all_tasks()
            if not item.done() and "wait_lost" in repr(item.get_coro())
        ]
    assert caught.value.stage is CommandStage.ACCEPTED
    assert leftover == []


async def test_invalid_session_playback_is_channel_not_found(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        killed = await channel.hangup()
        assert killed.body == "+OK\n"
        with pytest.raises(ChannelNotFound) as caught:
            await asyncio.wait_for(channel.playback("missing.wav", block=True), 1)
    assert caught.value.uuid == PRESENT
    assert esl_server.open_executions == {}
    assert any(
        item.startswith("api uuid_kill %s" % PRESENT) for item in _lines(esl_server)
    )
    assert not any("uuid_execute" in item for item in _lines(esl_server))


async def test_newline_in_uuid_is_not_sent(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        channel.uuid = "%s\napi status" % PRESENT
        with pytest.raises(ChannelError) as caught:
            await channel.playback("file.wav", block=False)
        assert not isinstance(caught.value, ChannelNotFound)
    assert all("api status" not in item for item in _lines(esl_server))


async def test_pending_wait_is_interrupted_by_connection_loss(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        task = asyncio.create_task(channel.wait("DTMF", timeout=5))
        await _until(
            lambda: any(
                not item.done() and "wait_lost" in repr(item.get_coro())
                for item in asyncio.all_tasks()
            )
        )
        await esl_server.fail(Fault.CLEAN_EOF, _connection_id(esl_server))
        with pytest.raises(ConnectionLost) as caught:
            await asyncio.wait_for(task, 1)
    assert caught.value.stage is CommandStage.NOT_SENT


async def test_wait_on_a_lost_connection_fails_immediately(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        await esl_server.fail(Fault.CLEAN_EOF, _connection_id(esl_server))
        await asyncio.wait_for(client._closed.wait(), 1)
        with pytest.raises(ConnectionLost) as caught:
            await channel.wait(ChannelState.PARK, timeout=5)
    assert caught.value.stage is CommandStage.NOT_SENT


async def test_cancelling_wait_drops_the_loss_task(esl_server: Simulator) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await client.get_channel(PRESENT)
        task = asyncio.create_task(channel.wait("DTMF", timeout=5))
        await _until(
            lambda: any(
                not item.done() and "wait_lost" in repr(item.get_coro())
                for item in asyncio.all_tasks()
            )
        )
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _until(
            lambda: not any(
                not item.done() and "wait_lost" in repr(item.get_coro())
                for item in asyncio.all_tasks()
            )
        )


async def test_get_channel_span_records_result_and_metrics_omit_uuid(
    esl_server: Simulator,
) -> None:
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    exporter = InMemorySpanExporter()
    provider: Any = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tap = _MetricTap()
    channel_operations_counter.add = tap.add  # type: ignore[method-assign]
    try:
        async with Inbound(
            esl_server.host, esl_server.port, esl_server.password
        ) as client:
            await client.get_channel(PRESENT)
            with pytest.raises(ChannelNotFound):
                await client.get_channel(ABSENT)
    finally:
        channel_operations_counter.add = tap._real  # type: ignore[method-assign]
    found = _spans(exporter, "get_channel")
    assert found
    assert found[-1].attributes["get_channel.result"] == "not_found"
    assert any(span.attributes.get("get_channel.result") == "found" for span in found)
    assert any(span.attributes.get("channel.uuid") == PRESENT for span in found)
    labels = tap.get_channel_labels()
    assert {item["result"] for item in labels} >= {"found", "not_found"}
    for item in labels:
        for key, value in item.items():
            assert "uuid" not in key.lower()
            assert PRESENT not in value
            assert ABSENT not in value


async def test_negative_unique_id_filter_blocks_playback_wait(
    esl_server: Simulator,
) -> None:
    """The veto stays. block=True does not wait. block=False still returns the ack."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("event plain ALL")
        await client.send("filter Unique-ID -%s" % PRESENT)
        channel = await client.get_channel(PRESENT)
        ack = await asyncio.wait_for(channel.playback("file.wav", block=False), 1)
        with pytest.raises(ChannelError, match="CHANNEL_EXECUTE_COMPLETE"):
            await channel.playback("blocked.wav", block=True, timeout=5)
    assert ack.get("Reply-Text") == "+OK"
    commands = _lines(esl_server)
    assert "filter Unique-ID -%s" % PRESENT in commands
    assert "filter Unique-ID %s" % PRESENT not in commands
    assert not any(item.startswith("filter delete") for item in commands)
    assert any("file.wav" in item for item in commands)
    assert not any("blocked.wav" in item for item in commands)


async def test_negative_event_name_filter_blocks_playback_wait(
    esl_server: Simulator,
) -> None:
    """Event-Name -CHANNEL_EXECUTE_COMPLETE is left in place and refuses the wait."""
    esl_server.seed_channel(PRESENT, name="loopback/9900-a", state="CS_EXECUTE")
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("event plain ALL")
        await client.send("filter Event-Name -CHANNEL_EXECUTE_COMPLETE")
        channel = await client.get_channel(PRESENT)
        with pytest.raises(ChannelError, match="CHANNEL_EXECUTE_COMPLETE"):
            await channel.playback("blocked.wav", block=True, timeout=5)
    commands = _lines(esl_server)
    assert "filter Event-Name -CHANNEL_EXECUTE_COMPLETE" in commands
    assert not any(item.startswith("filter delete") for item in commands)
    assert not any("blocked.wav" in item for item in commands)
