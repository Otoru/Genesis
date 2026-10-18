"""Application recovery after an ESL drop. No implicit retry or reconnect."""

import asyncio
from pathlib import Path
from typing import List, Tuple

from pytest_bdd import scenarios, then, when

from genesis import Channel, Inbound
from genesis.exceptions import ChannelNotFound, CommandStage, ConnectionLost
from genesis.types import ChannelState

from tests.bdd.world import World
from tests.simulator.faults import Fault

FEATURE = (
    Path(__file__).resolve().parents[1] / "features" / "connection_recovery.feature"
)
scenarios(str(FEATURE))

SEEDED = "3814d229-50d9-440e-b91d-8d0801ff615d"
MISSING = "61e6cf12-2e33-4491-812b-f5890c68ae50"
LOST_COMMAND = "api eval checkpoint"
STEP_TIMEOUT = 2


def _commands(world: World, connection_id: str) -> List[str]:
    return [item.text for item in world.journal.commands(connection_id)]


def _logins(world: World) -> List[str]:
    expected = "auth %s" % world.server.password
    found: List[str] = []
    for item in world.journal.commands():
        if item.text == expected and item.connection_id not in found:
            found.append(item.connection_id)
    return found


def _api_responses(world: World, connection_id: str) -> int:
    return sum(
        1
        for item in world.journal.events(connection_id)
        if item.frame.header("Content-Type") == "api/response"
    )


def _kill_command() -> str:
    return "api uuid_kill %s NORMAL_CLEARING" % SEEDED


async def _connect(world: World) -> Tuple[Inbound, str]:
    client = Inbound(world.server.host, world.server.port, world.server.password)
    try:
        await asyncio.wait_for(client.start(), STEP_TIMEOUT)
    except Exception:
        await client.stop()
        raise
    live = world.server.connection_ids
    if not live:
        await client.stop()
        raise RuntimeError("inbound did not attach")
    return client, live[-1]


async def _lose(world: World, client: Inbound, connection_id: str) -> None:
    await world.server.fail(Fault.DISCONNECT_BEFORE_REPLY, connection_id)
    try:
        await asyncio.wait_for(client.send(LOST_COMMAND), STEP_TIMEOUT)
    except ConnectionLost as exc:
        world.facts["lost"] = exc
        return
    world.facts["lost"] = None


async def _stop(client: Inbound, world: World, key: str) -> None:
    await client.stop()
    world.facts[key] = client.is_connected


@when("the local flow loses the connection before the reply", target_fixture="story")
def flow_loses_connection(world: World) -> World:
    async def _body() -> World:
        world.server.seed_channel(SEEDED, name="loopback/9900-a", application="park")
        client, connection_id = await _connect(world)
        world.facts["first_id"] = connection_id
        try:
            await _lose(world, client, connection_id)
        finally:
            await _stop(client, world, "connected")
        return world

    return world.run(_body())


@then("the flow stopped after ConnectionLost")
def flow_stopped(story: World) -> None:
    lost = story.facts["lost"]
    assert isinstance(lost, ConnectionLost)
    assert lost.stage is CommandStage.UNCONFIRMED
    assert story.facts["connected"] is False
    assert SEEDED in story.server.channels
    assert story.server.hangups == []


@then("the journal has no retry and no reconnect")
def no_retry_or_reconnect(story: World) -> None:
    first_id = story.facts["first_id"]
    assert isinstance(first_id, str)
    assert _commands(story, first_id) == [
        "auth %s" % story.server.password,
        LOST_COMMAND,
    ]
    assert _api_responses(story, first_id) == 0
    assert _logins(story) == [first_id]


@when(
    "a new inbound hangs up the seeded call after the connection drop",
    target_fixture="story",
)
def explicit_hangup(world: World) -> World:
    async def _body() -> World:
        world.server.seed_channel(SEEDED, name="loopback/9900-a", application="park")
        client, first_id = await _connect(world)
        world.facts["first_id"] = first_id
        try:
            await _lose(world, client, first_id)
        finally:
            await _stop(client, world, "connected")
        fresh, second_id = await _connect(world)
        world.facts["second_id"] = second_id
        try:
            channel = await asyncio.wait_for(fresh.get_channel(SEEDED), STEP_TIMEOUT)
            world.facts["channel"] = channel
            world.facts["observed_state"] = channel.state
            await asyncio.wait_for(channel.hangup(), STEP_TIMEOUT)
        finally:
            await _stop(fresh, world, "fresh_connected")
        return world

    return world.run(_body())


@then("that seeded call was hung up")
def seeded_call_hung_up(story: World) -> None:
    channel = story.facts["channel"]
    assert isinstance(channel, Channel)
    assert channel.uuid == SEEDED
    assert story.facts["observed_state"] is ChannelState.EXECUTE
    assert story.facts["fresh_connected"] is False
    assert story.server.hangups == [(SEEDED, "NORMAL_CLEARING")]
    assert SEEDED not in story.server.channels


@then("the journal has no retry of the lost command")
def lost_command_not_retried(story: World) -> None:
    first_id = story.facts["first_id"]
    second_id = story.facts["second_id"]
    assert isinstance(first_id, str) and isinstance(second_id, str)
    assert first_id != second_id
    assert _commands(story, first_id) == [
        "auth %s" % story.server.password,
        LOST_COMMAND,
    ]
    assert _api_responses(story, first_id) == 0
    second = _commands(story, second_id)
    assert LOST_COMMAND not in second
    assert second.count(_kill_command()) == 1
    assert _logins(story) == [first_id, second_id]


@when("a new inbound asks for a missing call", target_fixture="story")
def missing_call(world: World) -> World:
    async def _body() -> World:
        client, connection_id = await _connect(world)
        world.facts["first_id"] = connection_id
        world.facts["ended"] = False
        try:
            try:
                await asyncio.wait_for(client.get_channel(MISSING), STEP_TIMEOUT)
            except ChannelNotFound as exc:
                world.facts["missing"] = exc
                world.facts["ended"] = True
        finally:
            await _stop(client, world, "connected")
        return world

    return world.run(_body())


@then("the application ended on ChannelNotFound")
def ended_on_missing_channel(story: World) -> None:
    missing = story.facts.get("missing")
    assert story.facts["ended"] is True
    assert isinstance(missing, ChannelNotFound)
    assert not isinstance(missing, ConnectionLost)
    assert missing.uuid == MISSING
    assert story.facts["connected"] is False


@then("the journal has one connection and no hangup")
def single_connection_without_hangup(story: World) -> None:
    first_id = story.facts["first_id"]
    assert isinstance(first_id, str)
    commands = _commands(story, first_id)
    assert commands[0] == "auth %s" % story.server.password
    assert LOST_COMMAND not in commands
    assert _kill_command() not in commands
    assert all("uuid_kill" not in text for text in commands)
    assert _logins(story) == [first_id]
    assert story.server.hangups == []
