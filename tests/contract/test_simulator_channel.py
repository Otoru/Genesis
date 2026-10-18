"""Minimal channel-command replies. No media path is simulated."""

from typing import Tuple
from uuid import uuid4

from genesis import Inbound

from tests.simulator.server import Simulator


def _plain_bodies(server: Simulator) -> Tuple[bytes, ...]:
    return tuple(
        item.frame.body
        for item in server.journal.events()
        if item.frame.header("Content-Type") == "text/event-plain"
    )


async def _originate(client: Inbound, channel_uuid: str, dial: str) -> None:
    response = await client.send(
        "api originate {origination_uuid=%s}%s &park()" % (channel_uuid, dial)
    )
    assert response.body == "+OK %s\n" % channel_uuid


async def test_uuid_bridge_names_the_other_leg_and_does_not_emit_media(
    esl_server: Simulator,
) -> None:
    left = str(uuid4())
    right = str(uuid4())
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await _originate(client, left, "user/1000")
        await _originate(client, right, "user/2000")
        response = await client.send("api uuid_bridge %s %s" % (left, right))
    assert response.body == "+OK %s\n" % right
    assert "api uuid_bridge %s %s" % (left, right) in [
        item.text for item in esl_server.journal.commands()
    ]
    assert not any(
        b"Event-Name: CHANNEL_BRIDGE" in body for body in _plain_bodies(esl_server)
    )


async def test_uuid_bridge_unknown_leg_is_invalid_uuid(esl_server: Simulator) -> None:
    left = str(uuid4())
    missing = str(uuid4())
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await _originate(client, left, "user/1000")
        missing_leg = await client.send("api uuid_bridge %s %s" % (left, missing))
        usage = await client.send("api uuid_bridge only-one")
    assert missing_leg.body == "-ERR Invalid uuid\n"
    assert usage.body == "-USAGE: <uuid> <other_uuid>\n"


async def test_uuid_kill_known_leg_is_ok_and_unknown_is_rejected(
    esl_server: Simulator,
) -> None:
    present = str(uuid4())
    missing = str(uuid4())
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await _originate(client, present, "user/1000")
        killed = await client.send("api uuid_kill %s USER_BUSY" % present)
        rejected = await client.send("api uuid_kill %s USER_BUSY" % missing)
        usage = await client.send("api uuid_kill")
    assert killed.body == "+OK\n"
    assert (present, "USER_BUSY") in esl_server.hangups
    assert rejected.body == "-ERR No such channel!\n"
    assert (missing, "USER_BUSY") not in esl_server.hangups
    assert usage.body == "-USAGE: <uuid> [cause]\n"
