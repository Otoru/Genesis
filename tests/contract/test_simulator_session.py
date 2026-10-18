"""TCP checks for the loopback ESL simulator, against captured FreeSWITCH bytes."""

import asyncio
import re
from pathlib import Path
from typing import List, Sequence, Tuple

from genesis import Inbound, Outbound

from tests.simulator.codec import (
    MAX_CONTENT_LENGTH,
    ESLDecoder,
    ESLFrame,
    Header,
    decode_frames,
)
from tests.simulator.connection import _DISPATCH
from tests.simulator.faults import Fault
from tests.simulator.server import Simulator

PASSWORD = "lab-password"
REAL = Path(__file__).resolve().parents[1] / "references" / "real" / "1.11.3"
SYNTHETIC = Path(__file__).resolve().parents[1] / "references" / "synthetic"
EXECUTE_UUID = "6f7cc8de-4617-438b-afe3-864ed238cd5b"
EXECUTE_CHANNEL = "3814d229-50d9-440e-b91d-8d0801ff615d"
LOCK_UUID = "e8cfb6f5-c9f8-48f8-aac3-8eed44dafee0"
JOB_UUID = "0ae3e0fd-155c-4825-8a10-c1ed7f206b7e"


class Peer:
    """Minimal ESL client for one simulator connection."""

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.decoder = ESLDecoder()
        self.pending: List[ESLFrame] = []
        self.connection_id = ""

    @classmethod
    async def open(cls, simulator: Simulator, password: str = PASSWORD) -> "Peer":
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(simulator.host, simulator.port),
            1,
        )
        peer = cls(reader, writer)
        greeting = await peer.read()
        assert greeting.header("Content-Type") == "auth/request"
        assert greeting.body == b""
        before = len(simulator.journal.commands())
        await peer.send("auth %s" % password)
        if password == simulator.password:
            reply = await peer.read()
            assert reply.header("Reply-Text") == "+OK accepted"
        commands = simulator.journal.commands()[before:]
        matched = [item for item in commands if item.text.startswith("auth ")]
        assert matched
        peer.connection_id = matched[-1].connection_id
        return peer

    async def send(self, text: str) -> None:
        payload = text if text.endswith("\n\n") else text + "\n\n"
        self.writer.write(payload.encode("utf-8"))
        await self.writer.drain()

    async def read(self) -> ESLFrame:
        while not self.pending:
            chunk = await asyncio.wait_for(self.reader.read(65536), 2)
            if not chunk:
                raise ConnectionError("connection closed")
            self.pending.extend(self.decoder.feed(chunk))
        return self.pending.pop(0)

    async def close(self) -> None:
        self.writer.close()
        await self.writer.wait_closed()


def _plain_events(simulator: Simulator, connection_id: str) -> Tuple[ESLFrame, ...]:
    frames = []
    for item in simulator.journal.events(connection_id):
        if item.frame.header("Content-Type") == "text/event-plain":
            frames.append(item.frame)
    return tuple(frames)


def _event_names(body: bytes) -> Tuple[str, ...]:
    names = []
    for line in body.decode("utf-8").splitlines():
        if line.startswith("Event-Name: "):
            names.append(line.split(": ", 1)[1])
    return tuple(names)


async def _read_until_closed(reader: asyncio.StreamReader) -> bytes:
    chunks: List[bytes] = []
    while True:
        chunk = await asyncio.wait_for(reader.read(65536), 1)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


async def test_bad_auth_bytes_match_the_capture():
    captured = (REAL / "bad_auth.raw").read_bytes()
    async with Simulator(PASSWORD) as simulator:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(simulator.host, simulator.port),
            1,
        )
        writer.write(b"auth wrong\n\n")
        await writer.drain()
        received = await _read_until_closed(reader)
        writer.close()
        await writer.wait_closed()
    assert received == captured


async def test_fragmented_auth_still_accepts():
    async with Simulator(PASSWORD) as simulator:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(simulator.host, simulator.port),
            1,
        )
        peer = Peer(reader, writer)
        greeting = await peer.read()
        assert greeting.header("Content-Type") == "auth/request"
        writer.write(b"auth lab")
        await writer.drain()
        writer.write(b"-password\n\n")
        await writer.drain()
        reply = await peer.read()
        assert reply.header("Reply-Text") == "+OK accepted"
        await peer.close()


async def test_coalesced_api_eval_bodies_match_the_capture_lengths():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api eval alpha\n\napi eval beta\n\n")
        alpha = await peer.read()
        beta = await peer.read()
        await peer.close()
    assert alpha.header("Content-Type") == "api/response"
    assert alpha.body == b"alpha"
    assert alpha.header("Content-Length") == "5"
    assert beta.body == b"beta"
    assert beta.header("Content-Length") == "4"


async def test_unicode_api_body_matches_the_captured_hex():
    captured = decode_frames((REAL / "unicode_api_response.raw").read_bytes())[0]
    async with Simulator(PASSWORD) as simulator:
        async with Inbound(simulator.host, simulator.port, PASSWORD) as client:
            response = await client.send("api eval café-研究")
    assert response.body is not None
    assert response.body.encode("utf-8") == captured.body
    assert captured.body == bytes.fromhex("636166c3a92de7a094e7a9b6")


async def test_unknown_command_and_unknown_api_match_captured_replies():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("nope")
        command = await peer.read()
        await peer.send("api nope_research_cmd")
        api = await peer.read()
        await peer.close()
    assert command.headers == (
        ("Content-Type", "command/reply"),
        ("Reply-Text", "-ERR command not found"),
    )
    assert command.body == b""
    assert api.header("Content-Type") == "api/response"
    assert api.body == b"-ERR nope_research_cmd Command not found!\n"
    assert api.header("Content-Length") == "42"


async def test_two_connections_keep_separate_subscriptions_and_filters():
    headers: Sequence[Header] = (
        ("Event-Subclass", "esl.research.a"),
        ("Event-Name", "CUSTOM"),
        ("research-marker", "only-a"),
    )
    async with Simulator(PASSWORD) as simulator:
        peer_a = await Peer.open(simulator)
        peer_b = await Peer.open(simulator)
        await peer_a.send("event plain CUSTOM esl.research.a")
        enabled = await peer_a.read()
        assert enabled.header("Reply-Text") == "+OK event listener enabled plain"
        await peer_b.send("event plain CUSTOM esl.research.b")
        await peer_b.read()
        await peer_a.send("filter Event-Subclass esl.research.a")
        added = await peer_a.read()
        assert added.header("Reply-Text") == (
            "+OK filter added. [Event-Subclass]=[esl.research.a]"
        )
        await peer_b.send("filter Event-Subclass esl.research.b")
        await peer_b.read()
        await simulator.emit(headers)
        delivered = await peer_a.read()
        await peer_a.close()
        await peer_b.close()
    assert delivered.header("Content-Type") == "text/event-plain"
    assert b"research-marker: only-a" in delivered.body
    assert _plain_events(simulator, peer_a.connection_id)
    assert _plain_events(simulator, peer_b.connection_id) == ()
    captured = (REAL / "filter_isolation_a.raw").read_bytes()
    assert b"Event-Subclass: esl.research.a" in captured
    assert b"research-marker: only-a" in captured
    assert b"Event-Subclass: esl.research.a" in delivered.body


async def test_filter_delete_nixevent_noevents_and_inbound_linger_replies():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("filter Event-Subclass esl.research.a")
        await peer.read()
        await peer.send("filter delete Event-Subclass esl.research.a")
        deleted = await peer.read()
        await peer.send("event plain CUSTOM esl.research.a")
        await peer.read()
        await peer.send("nixevent CUSTOM")
        nixed = await peer.read()
        await peer.send("noevents")
        cleared = await peer.read()
        await peer.send("linger")
        linger = await peer.read()
        await peer.close()
    assert deleted.header("Reply-Text") == (
        "+OK filter deleted. [Event-Subclass][esl.research.a]"
    )
    assert "=" not in (deleted.header("Reply-Text") or "")
    assert nixed.header("Reply-Text") == "+OK events nixed"
    assert cleared.header("Reply-Text") == "+OK no longer listening for events"
    assert linger.header("Reply-Text") == "-ERR not controlling a session"


async def test_bgapi_job_uuid_is_on_the_reply_and_the_following_event():
    captured = (REAL / "bgapi_status.raw").read_bytes()
    assert ("Job-UUID: %s" % JOB_UUID).encode("ascii") in captured
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("event plain BACKGROUND_JOB")
        await peer.read()
        await peer.send("bgapi status\nJob-UUID: %s" % JOB_UUID)
        reply = await peer.read()
        event = await peer.read()
        await peer.close()
    assert reply.header("Reply-Text") == "+OK Job-UUID: %s" % JOB_UUID
    assert reply.header("Job-UUID") == JOB_UUID
    assert event.header("Content-Type") == "text/event-plain"
    text = event.body.decode("utf-8")
    assert "Event-Name: BACKGROUND_JOB" in text
    assert "Job-UUID: %s" % JOB_UUID in text
    assert "UP 0\n" in text


async def test_execute_frames_follow_the_capture_not_a_merged_body():
    captured = decode_frames((REAL / "sendmsg_log.raw").read_bytes())
    assert captured[0].header("Reply-Text") == "+OK"
    assert _event_names(captured[1].body) == ("CHANNEL_EXECUTE",)
    assert _event_names(captured[2].body) == ("CHANNEL_EXECUTE_COMPLETE",)
    execute_key = b"Application-UUID: " + EXECUTE_UUID.encode("ascii")
    assert execute_key in captured[1].body
    assert execute_key in captured[2].body
    assert b"Application-Data: INFO%20esl-research" in captured[1].body
    assert b"event-lock" not in (REAL / "event_lock.raw").read_bytes()
    async with Simulator(PASSWORD) as simulator:
        simulator.seed_channel(EXECUTE_CHANNEL, name="loopback/9900-a")
        peer = await Peer.open(simulator)
        await peer.send("event plain ALL")
        await peer.read()
        await peer.send(
            "\n".join(
                (
                    "sendmsg %s" % EXECUTE_CHANNEL,
                    "call-command: execute",
                    "execute-app-name: log",
                    "execute-app-arg: INFO esl-research",
                    "Event-UUID: %s" % EXECUTE_UUID,
                )
            )
        )
        reply = await peer.read()
        logged = await simulator.next_execution()
        assert logged.event_uuid == EXECUTE_UUID
        assert logged.application == "log"
        assert logged.data == "INFO esl-research"
        assert logged.lock is False
        await simulator.start_execution(logged)
        await simulator.complete_execution(logged)
        execute = await peer.read()
        complete = await peer.read()
        await peer.send(
            "\n".join(
                (
                    "sendmsg %s" % EXECUTE_CHANNEL,
                    "call-command: execute",
                    "execute-app-name: sleep",
                    "execute-app-arg: 100",
                    "event-lock: true",
                    "Event-UUID: %s" % LOCK_UUID,
                )
            )
        )
        await peer.read()
        locked_pending = await simulator.next_execution()
        assert locked_pending.event_uuid == LOCK_UUID
        assert locked_pending.lock is True
        assert locked_pending.channel_uuid == EXECUTE_CHANNEL
        await simulator.start_execution(locked_pending)
        await simulator.complete_execution(locked_pending)
        locked = await peer.read()
        locked_complete = await peer.read()
        await peer.close()
    assert reply.header("Reply-Text") == "+OK"
    assert _event_names(execute.body) == ("CHANNEL_EXECUTE",)
    assert _event_names(complete.body) == ("CHANNEL_EXECUTE_COMPLETE",)
    assert execute_key in execute.body
    assert execute_key in complete.body
    assert b"Application-Data: INFO%20esl-research" in execute.body
    lock_key = b"Application-UUID: " + LOCK_UUID.encode("ascii")
    assert b"event-lock" not in execute.body
    assert b"event-lock" not in complete.body
    assert b"event-lock" not in locked.body
    assert b"event-lock" not in locked_complete.body
    assert lock_key in locked.body
    assert lock_key in locked_complete.body


async def test_exit_or_drop_removes_one_peer_and_the_listener_stays_up():
    async with Simulator(PASSWORD) as simulator:
        staying = await Peer.open(simulator)
        leaving = await Peer.open(simulator)
        await leaving.send("exit")
        bye = await leaving.read()
        notice = await leaving.read()
        assert bye.header("Reply-Text") == "+OK bye"
        assert notice.header("Content-Type") == "text/disconnect-notice"
        goodbye = (
            b"Disconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n"
        )
        assert notice.body == goodbye
        await staying.send("api eval alpha")
        assert (await staying.read()).body == b"alpha"
        replacement = await Peer.open(simulator)
        await replacement.send("api eval beta")
        assert (await replacement.read()).body == b"beta"
        dropped = await Peer.open(simulator)
        await simulator.fail(Fault.DROP_CONNECTION, dropped.connection_id)
        try:
            await dropped.read()
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        else:
            raise AssertionError("dropped peer still returned a frame")
        await staying.send("api eval still")
        assert (await staying.read()).body == b"still"
        await staying.close()
        await replacement.close()
    captured_exit = (REAL / "full_exit.raw").read_bytes()
    assert b"Reply-Text: +OK bye" in captured_exit
    assert b"Content-Disposition: disconnect" in captured_exit


async def test_start_twice_raises_and_close_refuses_the_port():
    simulator = Simulator(PASSWORD)
    await simulator.start()
    port = simulator.port
    try:
        try:
            await simulator.start()
        except RuntimeError:
            pass
        else:
            raise AssertionError("second start() did not raise")
        assert simulator.port == port
        peer = await Peer.open(simulator)
        await peer.close()
    finally:
        await simulator.close()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", port), 1
        )
    except OSError:
        return
    writer.close()
    await writer.wait_closed()
    raise AssertionError("port %s still accepted a connection" % port)


async def test_scenario_emits_only_after_the_command_is_seen():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("event plain ALL")
        await peer.read()
        registered = asyncio.Event()
        task = asyncio.create_task(
            simulator.scenario.emit_after_command(
                lambda command: command.text == "api eval alpha"
                and command.connection_id == peer.connection_id,
                (("Event-Name", "CHANNEL_PARK"), ("Unique-ID", "leg-1")),
                registered=registered,
            )
        )
        await registered.wait()
        assert _plain_events(simulator, peer.connection_id) == ()
        await peer.send("api eval alpha")
        await task
        first = await peer.read()
        second = await peer.read()
        await peer.close()
    assert first.header("Content-Type") == "api/response"
    assert first.body == b"alpha"
    assert second.header("Content-Type") == "text/event-plain"
    assert b"Event-Name: CHANNEL_PARK" in second.body


async def test_event_can_be_written_before_the_reply():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("event plain ALL")
        await peer.read()
        simulator.scenario.before_reply(
            peer.connection_id,
            (("Event-Name", "CHANNEL_PARK"), ("Unique-ID", "leg-1")),
        )
        await peer.send("api eval alpha")
        first = await peer.read()
        second = await peer.read()
        await peer.close()
    assert first.header("Content-Type") == "text/event-plain"
    assert b"Event-Name: CHANNEL_PARK" in first.body
    assert second.body == b"alpha"


async def test_faults_are_opt_in_and_synthetic_bytes_stay_out_of_real_captures():
    short = (SYNTHETIC / "short_body.raw").read_bytes()
    mismatch = (SYNTHETIC / "bad_content_length.raw").read_bytes()
    rude = (REAL / "host_acl_rude_rejection.raw").read_bytes()
    assert not short.startswith(b"#")
    assert not mismatch.startswith(b"#")
    assert '"kind": "synthetic"' in (SYNTHETIC / "short_body.meta.json").read_text(
        encoding="utf-8"
    )
    assert '"kind": "real"' in (REAL / "host_acl_rude_rejection.meta.json").read_text(
        encoding="utf-8"
    )
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await simulator.fail(Fault.SHORT_BODY, peer.connection_id)
        await peer.send("api status")
        short_received = await asyncio.wait_for(peer.reader.read(65536), 1)
        await simulator.fail(Fault.BAD_CONTENT_LENGTH, peer.connection_id)
        await peer.send("api status")
        mismatch_received = await asyncio.wait_for(peer.reader.read(65536), 1)
        await simulator.fail(Fault.RUDE_REJECTION, peer.connection_id)
        await peer.send("api status")
        rude_received = await _read_until_closed(peer.reader)
    assert short_received == short
    assert mismatch_received == mismatch
    assert rude_received == rude
    assert b"Access Denied, go away.\n" in rude
    assert b"text/rude-rejection" not in short


async def test_stalled_reads_ignore_a_command_until_the_caller_cancels():
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        connection = simulator.connection(peer.connection_id)
        stall = asyncio.create_task(
            simulator.fail(Fault.STALL_READS, peer.connection_id)
        )
        await peer.send("api eval during-stall")
        await asyncio.wait_for(connection.stall_caught.wait(), 1)
        assert not any(
            "during-stall" in item.text
            for item in simulator.journal.commands(peer.connection_id)
        )
        stall.cancel()
        try:
            await stall
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("stall was not cancelled")
        await peer.send("api eval alpha")
        frame = await peer.read()
        await peer.close()
    assert frame.body == b"alpha"


async def test_bad_password_on_one_peer_leaves_the_other_authenticated():
    async with Simulator(PASSWORD) as simulator:
        good = await Peer.open(simulator)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(simulator.host, simulator.port),
            1,
        )
        other = Peer(reader, writer)
        greeting = await other.read()
        assert greeting.header("Content-Type") == "auth/request"
        others = [
            connection_id
            for connection_id in simulator.connection_ids
            if connection_id != good.connection_id
        ]
        assert len(others) == 1
        await simulator.fail(Fault.BAD_PASSWORD, others[0])
        await other.send("auth %s" % PASSWORD)
        rejected = await other.read()
        assert rejected.header("Reply-Text") == "-ERR invalid"
        await good.send("api eval alpha")
        assert (await good.read()).body == b"alpha"
        await good.close()


async def _accept_outbound(
    simulator: Simulator, full: bool
) -> Tuple[asyncio.AbstractServer, asyncio.Event, ESLFrame, Peer]:
    ready: asyncio.Future[Tuple[asyncio.StreamReader, asyncio.StreamWriter]] = (
        asyncio.get_running_loop().create_future()
    )
    hold = asyncio.Event()

    async def on_client(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if not ready.done():
            ready.set_result((reader, writer))
        await hold.wait()
        if not writer.is_closing():
            writer.close()

    server = await asyncio.start_server(on_client, "127.0.0.1", 0)
    sockets = server.sockets
    assert sockets is not None
    port = int(sockets[0].getsockname()[1])
    await simulator.connect_dialplan("127.0.0.1", port, full=full)
    reader, writer = await asyncio.wait_for(ready, 1)
    peer = Peer(reader, writer)
    await peer.send("connect")
    frame = await peer.read()
    return server, hold, frame, peer


async def test_outbound_full_and_single_channel_follow_the_captures():
    full_capture = decode_frames((REAL / "full_connect.raw").read_bytes())[0]
    plain_capture = decode_frames((REAL / "plain_connect.raw").read_bytes())[0]
    plain_exit = (REAL / "plain_exit.raw").read_bytes()
    assert full_capture.header("Control") == "full"
    assert plain_capture.header("Control") == "single-channel"
    assert full_capture.header("Reply-Text") == "%2BOK%0A"
    assert plain_capture.header("Reply-Text") == "%2BOK%0A"
    assert b"Reply-Text: -ERR command not found" in plain_exit
    async with Simulator(PASSWORD) as simulator:
        full_server, full_hold, full_frame, full_peer = await _accept_outbound(
            simulator, True
        )
        plain_server, plain_hold, plain_frame, plain_peer = await _accept_outbound(
            simulator, False
        )
        try:
            await full_peer.send("event plain ALL")
            full_event = await full_peer.read()
            await full_peer.send("api eval alpha")
            full_api = await full_peer.read()
            await full_peer.send("linger")
            full_linger = await full_peer.read()
            await plain_peer.send("myevents")
            myevents = await plain_peer.read()
            await plain_peer.send("event plain ALL")
            rejected_event = await plain_peer.read()
            await plain_peer.send("api status")
            rejected_api = await plain_peer.read()
        finally:
            full_hold.set()
            plain_hold.set()
            full_peer.writer.close()
            plain_peer.writer.close()
            full_server.close()
            plain_server.close()
            await full_server.wait_closed()
            await plain_server.wait_closed()
    assert full_frame.header("Control") == full_capture.header("Control")
    assert plain_frame.header("Control") == plain_capture.header("Control")
    assert full_frame.header("Reply-Text") == full_capture.header("Reply-Text")
    assert plain_frame.header("Reply-Text") == plain_capture.header("Reply-Text")
    assert full_frame.header("Socket-Mode") == "async"
    assert plain_frame.header("Event-Name") == "CHANNEL_DATA"
    assert full_event.header("Reply-Text") == "+OK event listener enabled plain"
    assert full_api.body == b"alpha"
    assert full_linger.header("Reply-Text") == "+OK will linger"
    assert myevents.header("Reply-Text") == "+OK Events Enabled"
    assert rejected_event.header("Reply-Text") == "-ERR command not found"
    assert rejected_api.header("Reply-Text") == "-ERR command not found"


async def test_genesis_outbound_without_full_is_rejected_for_event_plain_all():
    """Genesis sends event plain all when events stay at the default.

    FreeSWITCH without full answers that command with -ERR command not found.
    myevents is the command that enables events in that mode.
    """
    started = asyncio.Event()

    async def handler(session: object) -> None:
        del session
        started.set()

    application = Outbound(handler, "127.0.0.1", 0, events=True, linger=True)
    await application.start(block=False)
    server = application.server
    sockets = getattr(server, "sockets", None) if server is not None else None
    assert sockets is not None
    port = int(sockets[0].getsockname()[1])
    try:
        async with Simulator(PASSWORD) as simulator:
            connection_id = await simulator.connect_dialplan(
                "127.0.0.1", port, full=False
            )
            await asyncio.wait_for(started.wait(), 2)
            commands = [item.text for item in simulator.journal.commands(connection_id)]
            replies = [
                item.frame.header("Reply-Text")
                for item in simulator.journal.events(connection_id)
                if item.frame.header("Content-Type") == "command/reply"
            ]
    finally:
        await application.stop()
    assert "connect" in commands
    assert "event plain all" in commands
    assert any(item.startswith("filter Unique-ID ") for item in commands)
    assert "linger" in commands
    assert "myevents" not in commands
    assert "-ERR command not found" in replies
    assert "+OK will linger" in replies


async def test_bgapi_filter_and_sendevent_fanout_are_per_connection() -> None:
    """BACKGROUND_JOB honors filters. sendevent reaches every subscriber."""
    async with Simulator(PASSWORD) as simulator:
        alpha = await Peer.open(simulator)
        beta = await Peer.open(simulator)
        await alpha.send("event plain BACKGROUND_JOB CUSTOM marker")
        await alpha.read()
        await alpha.send("filter Job-Command status")
        await alpha.read()
        await beta.send("event plain BACKGROUND_JOB CUSTOM marker")
        await beta.read()
        await beta.send("filter Job-Command other")
        await beta.read()
        await alpha.send("bgapi status\nJob-UUID: %s" % JOB_UUID)
        alpha_reply = await alpha.read()
        alpha_job = await alpha.read()
        await beta.send("api eval drain-bgapi")
        beta_drain = await beta.read()
        await alpha.send("filter delete all")
        await alpha.read()
        await beta.send("filter delete all")
        await beta.read()
        await alpha.send("event plain CUSTOM marker")
        await alpha.read()
        await beta.send("event plain CUSTOM marker")
        await beta.read()
        await alpha.send(
            "sendevent CUSTOM\nEvent-Subclass: marker\nresearch-note: both\n\n"
        )
        alpha_ok = await alpha.read()
        alpha_event = await alpha.read()
        beta_event = await beta.read()
        await alpha.close()
        await beta.close()
    assert alpha_reply.header("Job-UUID") == JOB_UUID
    assert b"Event-Name: BACKGROUND_JOB" in alpha_job.body
    assert b"Job-Command: status" in alpha_job.body
    assert beta_drain.header("Content-Type") == "api/response"
    assert beta_drain.body == b"drain-bgapi"
    assert alpha_ok.header("Content-Type") == "command/reply"
    assert b"Event-Subclass: marker" in alpha_event.body
    assert b"research-note: both" in alpha_event.body
    assert beta_event.body == alpha_event.body


async def test_xml_and_json_event_formats_are_rejected() -> None:
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("event xml ALL")
        xml_reply = await peer.read()
        await peer.send("event json ALL")
        json_reply = await peer.read()
        connection = simulator.connection(peer.connection_id)
        await peer.send("api eval still-up")
        follow = await peer.read()
        await peer.close()
    assert xml_reply.header("Reply-Text") == "-ERR unsupported event format"
    assert json_reply.header("Reply-Text") == "-ERR unsupported event format"
    assert connection.all_events is False
    assert follow.body == b"still-up"


async def test_command_content_length_errors_do_not_wait_for_a_body() -> None:
    async with Simulator(PASSWORD) as simulator:
        peer = await Peer.open(simulator)
        await peer.send("api eval alpha\nContent-Length: no\n\n")
        invalid = await peer.read()
        await peer.close()
        second = await Peer.open(simulator)
        await second.send(
            "api eval alpha\nContent-Length: %s\n\n" % (MAX_CONTENT_LENGTH + 1)
        )
        capped = await second.read()
        fresh = await Peer.open(simulator)
        await fresh.send("api eval listener")
        alive = await fresh.read()
        await fresh.close()
    assert invalid.header("Reply-Text") == "-ERR invalid Content-Length"
    assert capped.header("Reply-Text") == "-ERR Content-Length exceeds %s" % (
        MAX_CONTENT_LENGTH,
    )
    assert alive.body == b"listener"


async def test_handler_exception_replies_and_leaves_the_listener_up() -> None:
    async def boom(conn: object, first: str, command: str) -> None:
        del conn, first, command
        raise RuntimeError("hidden")

    original = _DISPATCH["api"]
    _DISPATCH["api"] = boom
    try:
        async with Simulator(PASSWORD) as simulator:
            peer = await Peer.open(simulator)
            await peer.send("api eval alpha")
            failed = await peer.read()
            _DISPATCH["api"] = original
            await peer.send("api eval beta")
            recovered = await peer.read()
            await peer.close()
            later = await Peer.open(simulator)
            await later.send("api eval gamma")
            third = await later.read()
            await later.close()
    finally:
        _DISPATCH["api"] = original
    assert failed.header("Reply-Text") == "-ERR internal error"
    assert recovered.body == b"beta"
    assert third.body == b"gamma"


def test_simulator_package_source_does_not_import_genesis():
    root = Path(__file__).resolve().parents[1] / "simulator"
    pattern = re.compile(r"(?m)^\s*(import genesis\b|from genesis\b)")
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert pattern.search(text) is None
