"""Channel call-control against the loopback simulator."""

import asyncio
from typing import Optional, Tuple

import pytest

from genesis import Channel, Inbound, Outbound, Session
from genesis.exceptions import ChannelError, TimeoutError
from genesis.protocol.parser import ESLEvent
from genesis.types import ChannelState, EventHandler

from tests.simulator.server import Simulator

HeaderSet = Tuple[Tuple[str, str], ...]


def _lines(server: Simulator) -> Tuple[str, ...]:
    return tuple(item.text for item in server.journal.commands())


def _state_headers(channel_uuid: str, state: str) -> HeaderSet:
    return (
        ("Event-Name", "CHANNEL_STATE"),
        ("Unique-ID", channel_uuid),
        ("Channel-State", state),
        ("variable_test_key", "test_value"),
    )


def _answer_headers(channel_uuid: str) -> HeaderSet:
    return (
        ("Event-Name", "CHANNEL_ANSWER"),
        ("Unique-ID", channel_uuid),
    )


def _watch_state(
    client: Inbound, channel: Channel, expected: ChannelState
) -> asyncio.Event:
    seen: asyncio.Event = asyncio.Event()
    original = channel._state_handler

    async def wrapped(event: ESLEvent) -> None:
        original(event)
        if event.get("Unique-ID") == channel.uuid and channel.state == expected:
            seen.set()

    client.remove("CHANNEL_STATE", original)
    client.on("CHANNEL_STATE", wrapped)
    return seen


class _WaitGate:
    """Signals when ``Channel.wait`` has registered, then when each handler returns."""

    def __init__(self, client: Inbound) -> None:
        self.ready: asyncio.Event = asyncio.Event()
        self.state_done: asyncio.Event = asyncio.Event()
        self.answer_done: asyncio.Event = asyncio.Event()
        self._client = client
        self._original = client.on
        self._loop = asyncio.get_running_loop()

    def install(self) -> None:
        loop = self._loop
        state_done = self.state_done
        answer_done = self.answer_done
        original = self._original
        ready = self.ready

        def on(key: str, handler: EventHandler) -> None:
            def wrapped(event: ESLEvent) -> None:
                handler(event)
                if key == "CHANNEL_STATE":
                    loop.call_soon_threadsafe(state_done.set)
                elif key == "CHANNEL_ANSWER":
                    loop.call_soon_threadsafe(answer_done.set)

            original(key, wrapped)
            if key == "CHANNEL_ANSWER":
                ready.set()

        self._client.on = on  # type: ignore[method-assign]

    def restore(self) -> None:
        self._client.on = self._original  # type: ignore[method-assign]


async def _listen(
    channel: Channel, target: ChannelState, timeout: float = 1.0
) -> "asyncio.Task[Optional[ESLEvent]]":
    protocol = channel.protocol
    assert isinstance(protocol, Inbound)
    gate = _WaitGate(protocol)
    gate.install()
    task: asyncio.Task[Optional[ESLEvent]] = asyncio.create_task(
        channel.wait(target, timeout=timeout)
    )
    try:
        await asyncio.wait_for(gate.ready.wait(), 1)
    except BaseException:
        gate.restore()
        task.cancel()
        raise
    gate.restore()
    return task


def _require_uuid(channel: Channel) -> str:
    assert channel.uuid is not None
    return channel.uuid


async def test_channel_start(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
    expected = (
        "api originate {origination_uuid=%s,return_ring_ready=true}user/1000 &park()"
        % channel_uuid
    )
    assert expected in _lines(esl_server)
    assert esl_server.channels[channel_uuid] == "user/1000"


async def test_channel_hangup(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        response = await channel.hangup()
    assert response.body == "+OK\n"
    assert not str(response.get("Reply-Text", "")).startswith("+OK")
    assert "api uuid_kill %s NORMAL_CLEARING" % channel_uuid in _lines(esl_server)
    assert (channel_uuid, "NORMAL_CLEARING") in esl_server.hangups


async def test_channel_hangup_custon_cause(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        response = await channel.hangup("USER_BUSY")
    assert response.body == "+OK\n"
    assert "api uuid_kill %s USER_BUSY" % channel_uuid in _lines(esl_server)
    assert (channel_uuid, "USER_BUSY") in esl_server.hangups


async def test_channel_bridge_with_another_channel(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel_a = await Channel.create(client, "user/1000")
        channel_b = await Channel.create(client, "user/2000")
        left = _require_uuid(channel_a)
        right = _require_uuid(channel_b)
        response = await channel_a.bridge(channel_b)
    assert response.body == "+OK %s\n" % right
    assert not str(response.get("Reply-Text", "")).startswith("+OK")
    assert "api uuid_bridge %s %s" % (left, right) in _lines(esl_server)
    assert not any(
        b"Event-Name: CHANNEL_BRIDGE" in item.frame.body
        for item in esl_server.journal.events()
    )


async def test_channel_bridge_with_session(esl_server: Simulator) -> None:
    done: asyncio.Future[ESLEvent] = asyncio.get_running_loop().create_future()
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        left = _require_uuid(channel)

        async def handler(session: Session) -> None:
            try:
                result = await channel.bridge(session)
            except Exception as exc:
                if not done.done():
                    done.set_exception(exc)
                return
            if not done.done():
                done.set_result(result)

        app = Outbound(handler, "127.0.0.1", 0)
        await app.start(block=False)
        try:
            bound = app.server
            assert bound is not None
            assert bound.sockets
            port = int(bound.sockets[0].getsockname()[1])
            await esl_server.connect_dialplan("127.0.0.1", port, full=True)
            response = await asyncio.wait_for(done, 2)
        finally:
            await app.stop()
    assert response.body is not None
    other = response.body[len("+OK ") :].strip()
    assert response.body == "+OK %s\n" % other
    assert other in esl_server.sessions
    assert "api uuid_bridge %s %s" % (left, other) in _lines(esl_server)
    assert not any(
        b"Event-Name: CHANNEL_BRIDGE" in item.frame.body
        for item in esl_server.journal.events()
    )


async def test_channel_create_with_variables(esl_server: Simulator) -> None:
    variables = {
        "origination_caller_id_number": "11999999999",
        "origination_caller_id_name": "Test",
    }
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000", variables)
        channel_uuid = _require_uuid(channel)
    originate = next(line for line in _lines(esl_server) if "originate" in line)
    assert channel_uuid in originate
    assert "origination_caller_id_number=11999999999" in originate
    assert "origination_caller_id_name=Test" in originate
    assert "return_ring_ready=true" in originate


async def test_channel_create_variables_cannot_override_defaults(
    esl_server: Simulator,
) -> None:
    variables = {
        "origination_uuid": "should-not-override",
        "return_ring_ready": "false",
    }
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000", variables)
        channel_uuid = _require_uuid(channel)
    assert channel_uuid != "should-not-override"
    originate = next(line for line in _lines(esl_server) if "originate" in line)
    assert "origination_uuid=%s" % channel_uuid in originate
    assert "return_ring_ready=true" in originate
    assert "return_ring_ready=false" not in originate
    assert "should-not-override" not in originate


async def test_channel_wait_already_in_state(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        seen = _watch_state(client, channel, ChannelState.ROUTING)
        await esl_server.emit(_state_headers(channel_uuid, "CS_ROUTING"))
        await asyncio.wait_for(seen.wait(), 1)
        result = await channel.wait(ChannelState.ROUTING, timeout=1.0)
    assert result is None
    assert channel.state == ChannelState.ROUTING


async def test_channel_wait_already_hangup(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        seen = _watch_state(client, channel, ChannelState.HANGUP)
        await esl_server.emit(_state_headers(channel_uuid, "CS_HANGUP"))
        await asyncio.wait_for(seen.wait(), 1)
        result = await channel.wait(ChannelState.EXECUTE, timeout=1.0)
    assert result is None
    assert channel.state == ChannelState.HANGUP


async def test_channel_wait_timeout(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        with pytest.raises(TimeoutError, match="Channel did not reach EXECUTE"):
            await channel.wait(ChannelState.EXECUTE, timeout=0.1)


async def test_channel_wait_state_change(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        wait_task = await _listen(channel, ChannelState.ROUTING)
        await esl_server.emit(_state_headers(channel_uuid, "CS_ROUTING"))
        result = await wait_task
    assert result is not None
    assert result.get("Unique-ID") == channel_uuid
    assert channel.state == ChannelState.ROUTING


async def test_channel_wait_execute_with_answer(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        gate = _WaitGate(client)
        gate.install()
        wait_task: asyncio.Task[Optional[ESLEvent]] = asyncio.create_task(
            channel.wait(ChannelState.EXECUTE, timeout=1.0)
        )
        try:
            await asyncio.wait_for(gate.ready.wait(), 1)
            await esl_server.emit(_state_headers(channel_uuid, "CS_EXECUTE"))
            await asyncio.wait_for(gate.state_done.wait(), 1)
            await esl_server.emit(_answer_headers(channel_uuid))
            result = await wait_task
        finally:
            gate.restore()
            if not wait_task.done():
                wait_task.cancel()
    assert result is not None
    assert result.get("Event-Name") == "CHANNEL_STATE"
    assert channel.state == ChannelState.EXECUTE


async def test_channel_wait_execute_answer_first(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        gate = _WaitGate(client)
        gate.install()
        wait_task = asyncio.create_task(channel.wait(ChannelState.EXECUTE, timeout=1.0))
        try:
            await asyncio.wait_for(gate.ready.wait(), 1)
            await esl_server.emit(_answer_headers(channel_uuid))
            await asyncio.wait_for(gate.answer_done.wait(), 1)
            await esl_server.emit(_state_headers(channel_uuid, "CS_EXECUTE"))
            result = await wait_task
        finally:
            gate.restore()
            if not wait_task.done():
                wait_task.cancel()
    assert result is not None
    assert channel.state == ChannelState.EXECUTE


async def test_channel_wait_ignores_other_channel_events(
    esl_server: Simulator,
) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        other = await Channel.create(client, "user/2000")
        channel_uuid = _require_uuid(channel)
        other_uuid = _require_uuid(other)
        wait_task = await _listen(channel, ChannelState.ROUTING)
        await esl_server.emit(_state_headers(other_uuid, "CS_ROUTING"))
        await esl_server.emit(_state_headers(channel_uuid, "CS_ROUTING"))
        result = await wait_task
    assert result is not None
    assert result.get("Unique-ID") == channel_uuid
    assert channel.state == ChannelState.ROUTING


async def test_channel_state_update(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        assert channel.state == ChannelState.NEW
        seen = _watch_state(client, channel, ChannelState.EXECUTE)
        await esl_server.emit(_state_headers(channel_uuid, "CS_EXECUTE"))
        await asyncio.wait_for(seen.wait(), 1)
    assert channel.state == ChannelState.EXECUTE
    assert channel.context.get("variable_test_key") == "test_value"


async def test_h6_state_event_emitted_before_the_handler_is_missed(
    esl_server: Simulator,
) -> None:
    """Registration after the event was consumed does not see that event."""
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        client.remove("CHANNEL_STATE", channel._state_handler)
        await esl_server.emit(_state_headers(channel_uuid, "CS_ROUTING"))
        drained = await client.send("api eval drain-h6")
        assert drained.body == "drain-h6"
        assert any(
            channel_uuid.encode("ascii") in item.frame.body
            for item in esl_server.journal.events()
            if item.frame.header("Content-Type") == "text/event-plain"
        )
        assert channel.state == ChannelState.NEW
        seen = asyncio.Event()

        def handler(event: ESLEvent) -> None:
            if event.get("Unique-ID") == channel_uuid:
                seen.set()

        client.on("CHANNEL_STATE", handler)
        assert not seen.is_set()
        assert channel.state == ChannelState.NEW


async def test_channel_state_validation_bridge(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        seen = _watch_state(client, channel, ChannelState.DESTROY)
        await esl_server.emit(_state_headers(channel_uuid, "CS_DESTROY"))
        await asyncio.wait_for(seen.wait(), 1)
        other = await Channel.create(client, "user/2000")
        with pytest.raises(
            ChannelError, match="Cannot bridge channel in state DESTROY"
        ):
            await channel.bridge(other)


async def test_channel_state_validation_hangup(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        channel = await Channel.create(client, "user/1000")
        channel_uuid = _require_uuid(channel)
        seen = _watch_state(client, channel, ChannelState.DESTROY)
        await esl_server.emit(_state_headers(channel_uuid, "CS_DESTROY"))
        await asyncio.wait_for(seen.wait(), 1)
        response = await channel.hangup()
    assert response.body == "+OK\n"
    assert "api uuid_kill %s NORMAL_CLEARING" % channel_uuid in _lines(esl_server)


def test_channel_state_ordering() -> None:
    assert ChannelState.NEW < ChannelState.EXECUTE
    assert ChannelState.EXECUTE < ChannelState.HANGUP
    assert ChannelState.HANGUP < ChannelState.DESTROY
    assert ChannelState.DESTROY > ChannelState.NEW


def test_channel_state_from_freeswitch() -> None:
    assert ChannelState.from_freeswitch("CS_NEW") == ChannelState.NEW
    assert ChannelState.from_freeswitch("CS_EXECUTE") == ChannelState.EXECUTE
    assert ChannelState.from_freeswitch("CS_DESTROY") == ChannelState.DESTROY
    assert ChannelState.from_freeswitch("NEW") == ChannelState.NEW
