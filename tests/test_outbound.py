import asyncio
from asyncio import Queue, Event, TimeoutError
from typing import Awaitable, Any

try:
    from unittest.mock import AsyncMock
except ImportError:
    from mock import AsyncMock

from genesis import Outbound, Session
from genesis.protocol.parser import parse_headers


async def test_outbound_session_has_context(host, port, dialplan):
    buffer: Queue[dict[str, str]] = Queue(maxsize=1)

    async def handler(session: Session) -> None:
        await buffer.put(session.context)

    address = (host(), port())
    application = Outbound(handler, *address)
    await application.start(block=False)

    await dialplan.start(*address)

    got = await buffer.get()
    expected = {
        "Answer-State": "early",
        "Call-Direction": "inbound",
        "Caller-Caller-ID-Name": "1001",
        "Caller-Caller-ID-Number": "1001",
        "Caller-Channel-Answered-Time": "0",
        "Caller-Channel-Created-Time": "1209749769132614",
        "Caller-Channel-Hangup-Time": "0",
        "Caller-Channel-Name": "sofia/default/1001@10.0.1.100",
        "Caller-Channel-Transfer-Time": "0",
        "Caller-Context": "default",
        "Caller-Destination-Number": "886",
        "Caller-Dialplan": "XML",
        "Caller-Network-Addr": "10.0.1.241",
        "Caller-Privacy-Hide-Name": "no",
        "Caller-Privacy-Hide-Number": "no",
        "Caller-Profile-Index": "1",
        "Caller-Screen-Bit": "yes",
        "Caller-Source": "mod_sofia",
        "Caller-Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "Caller-Username": "1001",
        "Channel-Caller-ID-Name": "1001",
        "Channel-Caller-ID-Number": "1001",
        "Channel-Channel-Answered-Time": "0",
        "Channel-Channel-Created-Time": "1209749769132614",
        "Channel-Channel-Hangup-Time": "0",
        "Channel-Channel-Name": "sofia/default/1001@10.0.1.100",
        "Channel-Channel-Transfer-Time": "0",
        "Channel-Context": "default",
        "Channel-Destination-Number": "886",
        "Channel-Dialplan": "XML",
        "Channel-Name": "sofia/default/1001@10.0.1.100",
        "Channel-Network-Addr": "10.0.1.241",
        "Channel-Privacy-Hide-Name": "no",
        "Channel-Privacy-Hide-Number": "no",
        "Channel-Profile-Index": "1",
        "Channel-Read-Codec-Name": "G722",
        "Channel-Read-Codec-Rate": "16000",
        "Channel-Screen-Bit": "yes",
        "Channel-Source": "mod_sofia",
        "Channel-State": "CS_EXECUTE",
        "Channel-State-Number": "4",
        "Channel-Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "Channel-Username": "1001",
        "Channel-Write-Codec-Name": "G722",
        "Channel-Write-Codec-Rate": "16000",
        "Content-Type": "command/reply",
        "Control": "full",
        "Socket-Mode": "async",
        "Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "variable_accountcode": "1001",
        "variable_channel_name": "sofia/default/1001@10.0.1.100",
        "variable_domain_name": "10.0.1.100",
        "variable_effective_caller_id_name": "Extension 1001",
        "variable_effective_caller_id_number": "1001",
        "variable_endpoint_disposition": "EARLY MEDIA",
        "variable_local_media_ip": "10.0.1.100",
        "variable_local_media_port": "62258",
        "variable_mailbox": "1001",
        "variable_max_forwards": "70",
        "variable_open": "true",
        "variable_presence_id": "1001@10.0.1.100",
        "variable_read_codec": "G722",
        "variable_read_rate": "16000",
        "variable_remote_media_ip": "10.0.1.241",
        "variable_remote_media_port": "62258",
        "variable_sip_auth_realm": "10.0.1.100",
        "variable_sip_auth_username": "1001",
        "variable_sip_authorized": "true",
        "variable_sip_call_id": "3c2bb21af10b-ogphkonpwqet",
        "variable_sip_contact_host": "10.0.1.241",
        "variable_sip_contact_params": "line=nc7obl5w",
        "variable_sip_contact_port": "2048",
        "variable_sip_contact_uri": "1001@10.0.1.241:2048",
        "variable_sip_contact_user": "1001",
        "variable_sip_from_host": "10.0.1.100",
        "variable_sip_from_tag": "wrgb4s5idf",
        "variable_sip_from_uri": "1001@10.0.1.100",
        "variable_sip_from_user": "1001",
        "variable_sip_from_user_stripped": "1001",
        "variable_sip_h_P-Key-Flags": 'keys="3"',
        "variable_sip_mailbox": "1001",
        "variable_sip_req_host": "10.0.1.100",
        "variable_sip_req_params": "user=phone",
        "variable_sip_req_uri": "886@10.0.1.100",
        "variable_sip_req_user": "886",
        "variable_sip_to_host": "10.0.1.100",
        "variable_sip_to_params": "user=phone",
        "variable_sip_to_uri": "886@10.0.1.100",
        "variable_sip_to_user": "886",
        "variable_sip_user_agent": "snom300/7.1.30",
        "variable_sip_via_host": "10.0.1.241",
        "variable_sip_via_port": "2048",
        "variable_sip_via_rport": "2048",
        "variable_socket_host": "127.0.0.1",
        "variable_sofia_profile_domain_name": ["10.0.1.100", "10.0.1.100"],
        "variable_sofia_profile_name": "default",
        "variable_user_context": "default",
        "variable_user_name": "1001",
        "variable_write_codec": "G722",
        "variable_write_rate": "16000",
    }

    assert got == expected, "The call context is incorrect"
    await dialplan.stop()
    await application.stop()


async def test_outbound_session_send_answer_command(
    host, port, dialplan, monkeypatch, generic
):
    spider = AsyncMock()
    spider.return_value = parse_headers(generic)

    semaphore = Event()
    monkeypatch.setattr(Session, "sendmsg", spider)

    async def handler(session: Session) -> None:
        await session.channel.answer()
        semaphore.set()

    address = (host(), port())
    application = Outbound(handler, *address)

    await application.start(block=False)

    await dialplan.start(*address)

    await semaphore.wait()
    await dialplan.stop()
    await application.stop()

    spider.assert_called_with("execute", "answer", None, block=False, timeout=None)


async def test_outbound_session_send_park_command(
    host, port, dialplan, monkeypatch, generic
):
    spider = AsyncMock()
    spider.return_value = parse_headers(generic)

    semaphore = Event()
    monkeypatch.setattr(Session, "sendmsg", spider)

    async def handler(session: Session) -> None:
        await session.channel.park()
        semaphore.set()

    address = (host(), port())
    application = Outbound(handler, *address)

    await application.start(block=False)

    await dialplan.start(*address)

    await semaphore.wait()
    await dialplan.stop()
    await application.stop()

    spider.assert_called_with("execute", "park", None, block=False, timeout=None)


async def test_outbound_session_send_hangup_command(
    host, port, dialplan, monkeypatch, generic
):
    spider = AsyncMock()
    spider.return_value = parse_headers(generic)

    semaphore = Event()
    monkeypatch.setattr(Session, "sendmsg", spider)

    async def handler(session: Session) -> None:
        await session.channel.hangup()
        semaphore.set()

    address = (host(), port())
    application = Outbound(handler, *address)
    await application.start(block=False)

    await dialplan.start(*address)

    await semaphore.wait()
    await dialplan.stop()
    await application.stop()

    spider.assert_called_with(
        "execute", "hangup", "NORMAL_CLEARING", block=False, timeout=None
    )


async def test_outbound_session_sendmsg_parameters(
    host, port, dialplan, monkeypatch, generic
):
    """Test different parameter combinations for sendmsg."""
    spider = AsyncMock()
    spider.return_value = parse_headers(generic)
    monkeypatch.setattr(Session, "sendmsg", spider)

    # Add an Event to track completion
    test_complete = Event()

    test_cases: list[dict[str, Any]] = [
        {
            "args": ("execute", "playback", "/tmp/test.wav"),
            "kwargs": {"lock": True},
            "desc": "with lock",
        },
        {
            "args": ("execute", "playback", "/tmp/test.wav"),
            "kwargs": {"uuid": "test-uuid-1234"},
            "desc": "with uuid",
        },
        {
            "args": ("execute", "playback", "/tmp/test.wav"),
            "kwargs": {"event_uuid": "test-event-5678"},
            "desc": "with event_uuid",
        },
        {
            "args": ("execute", "playback", "/tmp/test.wav"),
            "kwargs": {"block": True},
            "desc": "with block",
        },
        {
            "args": ("execute", "playback", "/tmp/test.wav"),
            "kwargs": {"headers": {"X-Test": "value"}},
            "desc": "with headers",
        },
    ]

    async def handler(session: Session) -> None:
        for case in test_cases:
            args: tuple[str, str, str] = case["args"]
            kwargs: dict[str, Any] = case["kwargs"]
            await session.sendmsg(*args, **kwargs)
        # Signal that all calls are complete
        test_complete.set()

    address = (host(), port())
    app = Outbound(handler, *address)

    await app.start(block=False)

    await dialplan.start(*address)

    # Wait for all calls to complete before stopping
    await test_complete.wait()

    await app.stop()
    await dialplan.stop()

    # Verify all calls were made with correct parameters
    for case in test_cases:
        expected_args = case["args"]
        expected_kwargs = case["kwargs"]
        spider.assert_any_call(*expected_args, **expected_kwargs)


async def test_outbound_handler_options(host, port, dialplan, monkeypatch, generic):
    """Test that handler options (events, linger) control connection setup commands."""
    spider = AsyncMock()
    spider.return_value = {"Socket-Mode": "async"}
    monkeypatch.setattr(Session, "send", spider)

    semaphore = Event()

    async def handler(session: Session) -> None:
        semaphore.set()

    address = (host(), port())
    app = Outbound(handler, *address, events=True, linger=True)

    await app.start(block=False)

    await dialplan.start(*address)

    await semaphore.wait()
    await app.stop()
    await dialplan.stop()

    calls = [call.args[0] for call in spider.call_args_list]

    assert "connect" in calls
    assert "myevents" not in calls
    assert "linger" in calls
    assert "event plain all" in calls

    has_filter = any(c.startswith("filter Unique-ID") for c in calls)
    assert has_filter, f"Expected filter command in calls: {calls}"


async def test_outbound_session_helpers(host, port, dialplan, monkeypatch, generic):
    """Test session helper methods (log, playback, say, play_and_get_digits)."""
    spider = AsyncMock()
    spider.return_value = parse_headers(generic)
    monkeypatch.setattr(Session, "sendmsg", spider)

    test_complete = Event()

    async def handler(session: Session) -> None:
        # Test log
        await session.channel.log("INFO", "test message")

        # Test playback
        await session.channel.playback("/tmp/file.wav")

        # Test say
        await session.channel.say("123", kind="NUMBER", method="pronounced")

        # Test play_and_get_digits
        await session.channel.play_and_get_digits(
            tries=3,
            timeout=5000,
            terminators="#",
            file="/tmp/prompt.wav",
            minimal=1,
            maximum=4,
            var_name="my_digits",
            regexp="\\d+",
            digit_timeout=2000,
        )

        test_complete.set()

    address = (host(), port())
    app = Outbound(handler, *address)

    await app.start(block=False)

    await dialplan.start(*address)

    await test_complete.wait()
    await app.stop()
    await dialplan.stop()

    spider.assert_any_call(
        "execute", "log", "INFO test message", block=False, timeout=None
    )
    spider.assert_any_call(
        "execute", "playback", "/tmp/file.wav", block=True, timeout=None
    )
    spider.assert_any_call(
        "execute",
        "say",
        "en NUMBER pronounced FEMININE 123",
        block=True,
        timeout=None,
    )

    # Expected arguments for play_and_get_digits based on the call above
    # ordered_arguments in source: minimal, maximum, tries, timeout, terminators, file, invalid_file, var_name, regexp, digit_timeout, transfer_on_failure
    expected_pagd_args = "1 4 3 5000 # /tmp/prompt.wav  my_digits \\d+ 2000 "
    spider.assert_any_call(
        "execute",
        "play_and_get_digits",
        expected_pagd_args,
        block=True,
        timeout=None,
    )


async def test_outbound_blocking_command(host, port, dialplan, generic):
    """Test that blocking commands wait for completion event."""
    test_complete = Event()
    event_uuid_holder = {"uuid": None}

    async def wait_for_execute_event_uuid(dialplan, timeout: float = 1.0) -> str:
        """Wait for an execute command to be received and return its event UUID."""
        start_time = asyncio.get_event_loop().time()
        async with dialplan.execute_event_condition:
            while True:
                if dialplan.pending_execute_events:
                    event_uuid = next(iter(dialplan.pending_execute_events.keys()))
                    del dialplan.pending_execute_events[event_uuid]
                    return event_uuid

                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError("No execute command received within timeout")

                remaining_timeout = timeout - elapsed
                try:
                    await asyncio.wait_for(
                        dialplan.execute_event_condition.wait(),
                        timeout=remaining_timeout,
                    )
                except asyncio.TimeoutError:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    raise TimeoutError("No execute command received within timeout")

    async def handler(session: Session) -> None:
        playback_task = asyncio.create_task(
            session.channel.playback("/tmp/blocking.wav", block=True)
        )

        event_uuid = await wait_for_execute_event_uuid(dialplan, timeout=1.0)
        event_uuid_holder["uuid"] = event_uuid
        await dialplan.broadcast(
            {
                "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
                "Application-UUID": event_uuid,
                "Unique-ID": session.uuid,
            }
        )

        event = await playback_task
        assert event["Event-Name"] == "CHANNEL_EXECUTE_COMPLETE"
        test_complete.set()

    address = (host(), port())
    app = Outbound(handler, *address)

    await app.start(block=False)

    await dialplan.start(*address)

    await test_complete.wait()
    await app.stop()
    await dialplan.stop()


async def test_outbound_blocking_command_timeout(host, port, dialplan, generic):
    """Test that blocking commands raise TimeoutError if event doesn't arrive."""
    test_complete = Event()

    async def handler(session: Session) -> None:
        try:
            await session.channel.playback(
                "/tmp/timeout.wav", block=True, timeout=0.001
            )
        except TimeoutError:
            test_complete.set()
        except Exception as e:
            print(f"Caught unexpected exception: {e}")

    address = (host(), port())
    app = Outbound(handler, *address)

    await app.start(block=False)

    await dialplan.start(*address)

    try:
        await asyncio.wait_for(test_complete.wait(), timeout=1.0)
    except asyncio.TimeoutError:
        assert False, "Blocking command did not timeout as expected"
    await app.stop()
    await dialplan.stop()
