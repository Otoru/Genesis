"""Recovery wire contracts for the loopback ESL simulator.

Assertions use the simulator codec and the captured FreeSWITCH frames.
The simulator does not import genesis.
"""

import asyncio
from typing import List

import pytest

from tests.contract.test_simulator_session import PASSWORD, REAL, Peer, _accept_outbound
from tests.simulator.codec import ESLFrame, IncompleteFrame, decode_frames
from tests.simulator.faults import Fault
from tests.simulator.server import Simulator

PRESENT = "3814d229-50d9-440e-b91d-8d0801ff615d"
ABSENT = "61e6cf12-2e33-4491-812b-f5890c68ae50"
EVENT = "439c369d-8977-4758-beb7-458d4f4a2ed0"


def _plain(simulator: Simulator, connection_id: str) -> List[ESLFrame]:
    frames = []
    for item in simulator.journal.events(connection_id):
        if item.frame.header("Content-Type") == "text/event-plain":
            frames.append(item.frame)
    return frames


async def _read_until_closed(reader: asyncio.StreamReader) -> bytes:
    chunks: List[bytes] = []
    while True:
        chunk = await asyncio.wait_for(reader.read(65536), 1)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _execute(channel_uuid: str, event_uuid: str) -> str:
    return "\n".join(
        (
            "sendmsg %s" % channel_uuid,
            "call-command: execute",
            "execute-app-name: log",
            "execute-app-arg: INFO esl-research",
            "Event-UUID: %s" % event_uuid,
        )
    )


async def test_absent_uuid_exists_body_matches_the_capture() -> None:
    captured = decode_frames((REAL / "uuid_exists_false.raw").read_bytes())[0]
    assert captured.body == b"false"
    assert captured.body.endswith(b"\n") is False
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api uuid_exists 61e6cf12-2e33-4491-812b-f5890c68ae50")
        reply = await peer.read()
        await peer.close()
    assert reply.header("Content-Type") == "api/response"
    assert reply.body == captured.body
    assert reply.header("Content-Length") == captured.header("Content-Length")


async def test_seeded_channel_uuid_exists_matches_the_capture() -> None:
    captured = decode_frames((REAL / "uuid_exists_true.raw").read_bytes())[0]
    assert captured.body == b"true"
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        peer = await Peer.open(simulator)
        await peer.send("api uuid_exists %s" % PRESENT)
        present = await peer.read()
        await peer.send("api uuid_exists")
        empty = await peer.read()
        await peer.close()
    assert present.body == captured.body
    assert present.header("Content-Length") == "4"
    assert empty.body == b"false"


async def test_uuid_dump_absent_and_usage_match_the_observed_bodies() -> None:
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api uuid_dump %s" % ABSENT)
        missing = await peer.read()
        await peer.send("api uuid_dump")
        usage = await peer.read()
        await peer.close()
    assert missing.header("Content-Type") == "api/response"
    assert missing.body == b"-ERR No such channel!\n"
    assert usage.body == b"-USAGE: <uuid> [format]\n"


async def test_default_uuid_dump_is_url_encoded_txt_not_bracketed_plain() -> None:
    txt = (REAL / "uuid_dump_txt_note.txt").read_bytes()
    plain = (REAL / "uuid_dump_plain.txt").read_bytes()
    assert b"variable_research_note: caf%C3%A9%20test\n" in txt
    assert b"Event-Name: CHANNEL_DATA\n" in txt
    assert b"Event-Name: [CHANNEL_DATA]" not in txt
    assert b"Event-Name: [CHANNEL_DATA]\n" in plain
    assert b"Channel-State: [CS_EXECUTE]\n" in plain
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(
            PRESENT,
            name="loopback/9900-a",
            state="CS_EXECUTE",
            call_state="ACTIVE",
            answer_state="answered",
            application="park",
            variables={"variable_research_note": "café test"},
        )
        peer = await Peer.open(simulator)
        await peer.send("api uuid_dump %s" % PRESENT)
        default = await peer.read()
        await peer.send("api uuid_dump %s txt" % PRESENT)
        explicit = await peer.read()
        await peer.send("api uuid_dump %s plain" % PRESENT)
        bracketed = await peer.read()
        await peer.close()
    assert default.header("Content-Type") == "api/response"
    assert default.body.startswith(b"Event-Name: CHANNEL_DATA\n")
    assert b"Event-Name: [CHANNEL_DATA]" not in default.body
    assert b"variable_research_note: caf%C3%A9%20test\n" in default.body
    assert b"variable_current_application: park\n" in default.body
    assert b"Unique-ID: %s\n" % PRESENT.encode("ascii") in default.body
    assert b"Event-Sequence: " in default.body
    assert explicit.body != default.body
    assert b"Event-Sequence: " in explicit.body
    assert b"variable_research_note: caf%C3%A9%20test\n" in explicit.body
    assert bracketed.body.startswith(b"Event-Name: [CHANNEL_DATA]\n")
    assert b"Channel-State: [CS_EXECUTE]\n" in bracketed.body
    assert "variable_research_note: [café test]\n".encode("utf-8") in bracketed.body
    assert b"caf%C3%A9" not in bracketed.body


async def test_uuid_kill_removes_the_channel_from_a_later_exists() -> None:
    captured_ok = b"+OK\n"
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a")
        peer = await Peer.open(simulator)
        await peer.send("api uuid_kill %s NORMAL_CLEARING" % PRESENT)
        killed = await peer.read()
        await peer.send("api uuid_exists %s" % PRESENT)
        exists = await peer.read()
        await peer.send("api uuid_dump %s" % PRESENT)
        dump = await peer.read()
        await peer.send("api uuid_kill %s" % ABSENT)
        rejected = await peer.read()
        await peer.close()
    assert killed.body == captured_ok
    assert (PRESENT, "NORMAL_CLEARING") in simulator.hangups
    assert exists.body == b"false"
    assert dump.body == b"-ERR No such channel!\n"
    assert rejected.body == b"-ERR No such channel!\n"
    assert PRESENT not in simulator.channels


def test_captured_race_dump_is_three_frames() -> None:
    frames = decode_frames((REAL / "race_dump.raw").read_bytes())
    assert [frame.header("Content-Type") for frame in frames] == [
        "api/response",
        "text/event-plain",
        "text/event-plain",
    ]
    assert frames[0].body.startswith(b"Event-Name: [CHANNEL_DATA]\n")
    assert b"Event-Name: CHANNEL_EXECUTE\n" in frames[1].body
    assert b"Event-Name: CHANNEL_EXECUTE_COMPLETE\n" in frames[2].body
    key = b"Application-UUID: " + EVENT.encode("ascii")
    assert key in frames[1].body
    assert key in frames[2].body
    assert key not in frames[0].body
    assert b"Application-Response: _none_" in frames[2].body


async def test_uuid_execute_is_not_an_api() -> None:
    captured = decode_frames((REAL / "uuid_execute_missing.raw").read_bytes())
    assert captured[0].body == b"-ERR uuid_execute Command not found!\n"
    assert captured[1].body == captured[0].body
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api uuid_execute")
        bare = await peer.read()
        await peer.send("api uuid_execute %s log INFO esl-research" % ABSENT)
        with_args = await peer.read()
        await peer.close()
    assert bare.body == captured[0].body
    assert with_args.body == captured[1].body


async def test_piped_eval_matches_the_capture() -> None:
    captured = decode_frames((REAL / "piped_eval.raw").read_bytes())
    assert [frame.body for frame in captured] == [b"alpha", b"beta"]
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api eval alpha\n\napi eval beta\n\n")
        alpha = await peer.read()
        beta = await peer.read()
        await peer.close()
    assert alpha.body == captured[0].body
    assert alpha.header("Content-Length") == "5"
    assert beta.body == captured[1].body
    assert beta.header("Content-Length") == "4"


async def test_a_new_connection_sees_the_same_channel() -> None:
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        first = await Peer.open(simulator)
        await first.send("api uuid_exists %s" % PRESENT)
        assert (await first.read()).body == b"true"
        await first.close()
        second = await Peer.open(simulator)
        await second.send("api uuid_dump %s" % PRESENT)
        dump = await second.read()
        await second.send("filter Unique-ID other-leg")
        added = await second.read()
        await simulator.emit(
            (("Event-Name", "CHANNEL_PARK"), ("Unique-ID", PRESENT)),
            connection_id=second.connection_id,
        )
        await second.send("api uuid_exists %s" % PRESENT)
        exists = await second.read()
        await second.close()
    assert b"Unique-ID: %s\n" % PRESENT.encode("ascii") in dump.body
    assert b"variable_current_application: park\n" in dump.body
    assert added.header("Reply-Text") == "+OK filter added. [Unique-ID]=[other-leg]"
    assert _plain(simulator, second.connection_id) == []
    assert exists.body == b"true"


async def test_a_new_connection_does_not_replay_a_delivered_event() -> None:
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        first = await Peer.open(simulator)
        await first.send("event plain ALL")
        await first.read()
        await simulator.emit((("Event-Name", "CHANNEL_PARK"), ("Unique-ID", PRESENT)))
        parked = await first.read()
        await first.close()
        second = await Peer.open(simulator)
        await second.send("event plain ALL")
        await second.read()
        await second.send("api uuid_dump %s" % PRESENT)
        dump = await second.read()
        await second.close()
    assert b"Event-Name: CHANNEL_PARK" in parked.body
    assert _plain(simulator, second.connection_id) == []
    assert second.pending == []
    assert b"CHANNEL_PARK" not in dump.body
    assert b"Event-Name: CHANNEL_DATA\n" in dump.body


async def test_sendmsg_stays_pending_until_the_scenario_starts_it() -> None:
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        peer = await Peer.open(simulator)
        await peer.send("event plain ALL")
        await peer.read()
        await peer.send(_execute(PRESENT, EVENT))
        ack = await peer.read()
        pending = await simulator.next_execution()
        await peer.send("api uuid_dump %s" % PRESENT)
        dump = await peer.read()
        assert _plain(simulator, peer.connection_id) == []
        await simulator.start_execution(pending)
        started = await peer.read()
        await simulator.complete_execution(pending)
        finished = await peer.read()
        await peer.close()
    assert ack.header("Reply-Text") == "+OK"
    assert pending.event_uuid == EVENT
    assert pending.channel_uuid == PRESENT
    assert pending.application == "log"
    assert b"CHANNEL_EXECUTE" not in dump.body
    assert b"variable_current_application: park\n" in dump.body
    assert started.header("Content-Type") == "text/event-plain"
    assert b"Event-Name: CHANNEL_EXECUTE\n" in started.body
    assert b"Application-UUID: %s\n" % EVENT.encode("ascii") in started.body
    assert b"Application-Data: INFO%20esl-research\n" in started.body
    assert b"Event-Name: CHANNEL_EXECUTE_COMPLETE\n" in finished.body
    assert b"Application-UUID: %s\n" % EVENT.encode("ascii") in finished.body
    assert b"Application-Response: _none_\n" in finished.body
    assert dump.header("Content-Type") == "api/response"
    assert started.body != dump.body


async def test_channel_disappears_after_the_configured_lookup() -> None:
    other = "dc297fe0-7761-4226-b7cb-19ae8ec93968"
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        simulator.seed_channel(other, name="loopback/9900-b")
        simulator.disappear_after(PRESENT, 1)
        simulator.disappear_after(other, 0)
        peer = await Peer.open(simulator)
        await peer.send("api uuid_exists %s" % PRESENT)
        still_here = await peer.read()
        await peer.send("api uuid_exists %s" % other)
        already_gone = await peer.read()
        await peer.send("api uuid_dump %s" % PRESENT)
        dumped = await peer.read()
        await peer.send("api uuid_exists %s" % PRESENT)
        after = await peer.read()
        await peer.close()
    assert still_here.body == b"true"
    assert already_gone.body == b"false"
    assert dumped.body == b"-ERR No such channel!\n"
    assert after.body == b"false"
    assert PRESENT not in simulator.channels
    assert other not in simulator.channels


async def test_disconnect_before_reply_writes_nothing() -> None:
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a")
        peer = await Peer.open(simulator)
        await simulator.fail(Fault.DISCONNECT_BEFORE_REPLY, peer.connection_id)
        await peer.send("api uuid_exists %s" % PRESENT)
        received = await _read_until_closed(peer.reader)
    commands = [item.text for item in simulator.journal.commands(peer.connection_id)]
    replies = [
        item.frame.header("Content-Type")
        for item in simulator.journal.events(peer.connection_id)
    ]
    assert received == b""
    assert any(item.startswith("api uuid_exists ") for item in commands)
    assert "api/response" not in replies
    assert "text/disconnect-notice" not in replies


async def test_ack_then_disconnect_leaves_execution_pending_for_a_new_socket() -> None:
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(PRESENT, name="loopback/9900-a", application="park")
        peer = await Peer.open(simulator)
        await peer.send("event plain ALL")
        await peer.read()
        await simulator.fail(Fault.ACK_THEN_DISCONNECT, peer.connection_id)
        await peer.send(_execute(PRESENT, EVENT))
        ack = await peer.read()
        with pytest.raises(ConnectionError):
            await peer.read()
        pending = simulator.open_executions[EVENT]
        assert _plain(simulator, peer.connection_id) == []
        fresh = await Peer.open(simulator)
        await fresh.send("event plain CHANNEL_EXECUTE CHANNEL_EXECUTE_COMPLETE")
        await fresh.read()
        await fresh.send("api uuid_dump %s" % PRESENT)
        before = await fresh.read()
        await simulator.start_execution(pending, connection_id=fresh.connection_id)
        started = await fresh.read()
        await fresh.send("api uuid_dump %s" % PRESENT)
        during = await fresh.read()
        await simulator.complete_execution(pending, connection_id=fresh.connection_id)
        finished = await fresh.read()
        await fresh.close()
    assert ack.header("Reply-Text") == "+OK"
    assert ack.header("Content-Type") == "command/reply"
    assert before.header("Content-Type") == "api/response"
    assert b"variable_current_application: park\n" in before.body
    assert EVENT.encode("ascii") not in before.body
    assert b"Event-Name: CHANNEL_EXECUTE\n" in started.body
    assert b"Application-UUID: %s\n" % EVENT.encode("ascii") in started.body
    assert during.header("Content-Type") == "api/response"
    assert b"Event-Name: CHANNEL_EXECUTE" not in during.body
    assert b"variable_current_application: log\n" in during.body
    assert b"Event-Name: CHANNEL_EXECUTE_COMPLETE\n" in finished.body
    assert b"Application-UUID: %s\n" % EVENT.encode("ascii") in finished.body
    assert EVENT not in simulator.open_executions


async def test_truncated_reply_is_not_a_complete_frame() -> None:
    captured = (REAL / "uuid_exists_false.raw").read_bytes()
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await simulator.fail(Fault.TRUNCATED_REPLY, peer.connection_id)
        await peer.send("api uuid_exists %s" % ABSENT)
        received = await _read_until_closed(peer.reader)
    assert received == captured[:-1]
    assert received != captured
    with pytest.raises(IncompleteFrame):
        decode_frames(received)


async def test_clean_eof_sends_no_disconnect_notice() -> None:
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        marked = len(simulator.journal.events(peer.connection_id))
        await simulator.fail(Fault.CLEAN_EOF, peer.connection_id)
        received = await _read_until_closed(peer.reader)
        later = simulator.journal.events(peer.connection_id)[marked:]
    assert received == b""
    assert later == ()
    assert b"disconnect-notice" not in received


async def test_sendmsg_unknown_uuid_matches_the_captured_reply() -> None:
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send(_execute(ABSENT, EVENT))
        reply = await peer.read()
        await peer.send(
            "\n".join(
                (
                    "sendmsg",
                    "call-command: execute",
                    "execute-app-name: log",
                    "Event-UUID: %s" % EVENT,
                )
            )
        )
        bare = await peer.read()
        await peer.close()
    assert reply.header("Content-Type") == "command/reply"
    assert reply.body == b""
    assert reply.header("Reply-Text") == "-ERR invalid session id [%s]" % ABSENT
    assert bare.header("Reply-Text") == "-ERR invalid session id []"
    assert simulator.open_executions == {}


async def test_outbound_session_is_a_channel_until_uuid_kill() -> None:
    async with Simulator(PASSWORD) as simulator:
        server, hold, frame, peer = await _accept_outbound(simulator, True)
        try:
            session_uuid = frame.header("Unique-ID")
            assert session_uuid is not None
            inbound = await Peer.open(simulator)
            await inbound.send("api uuid_exists %s" % session_uuid)
            exists = await inbound.read()
            await peer.send(
                "\n".join(
                    (
                        "sendmsg",
                        "call-command: execute",
                        "execute-app-name: log",
                        "Event-UUID: %s" % EVENT,
                    )
                )
            )
            controlled = await peer.read()
            await peer.send(_execute(session_uuid, EVENT))
            addressed = await peer.read()
            await inbound.send("api uuid_kill %s NORMAL_CLEARING" % session_uuid)
            killed = await inbound.read()
            await inbound.send("api uuid_exists %s" % session_uuid)
            gone = await inbound.read()
            await peer.send(_execute(session_uuid, EVENT))
            rejected = await peer.read()
            await inbound.close()
        finally:
            hold.set()
            peer.writer.close()
            server.close()
            await server.wait_closed()
    assert exists.body == b"true"
    assert controlled.header("Reply-Text") == "+OK"
    assert addressed.header("Reply-Text") == "+OK"
    assert killed.body == b"+OK\n"
    assert gone.body == b"false"
    assert rejected.header("Reply-Text") == (
        "-ERR invalid session id [%s]" % session_uuid
    )
    assert session_uuid not in simulator.sessions
    assert session_uuid not in simulator.channels
    assert session_uuid not in simulator.records
