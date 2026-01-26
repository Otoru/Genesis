import asyncio

from pytest import mark

from genesis import Outbound, Session


@mark.asyncio
async def test_on_dtmf_specific_digit(host, port, dialplan):
    """Test onDTMF decorator with specific digit filter."""
    received = asyncio.Event()
    handler_started = asyncio.Event()
    test_complete = asyncio.Event()
    captured_digits = []

    async def handler(session: Session) -> None:
        @session.channel.onDTMF("1")
        async def on_digit(digit: str):
            captured_digits.append(digit)
            received.set()

        handler_started.set()
        await test_complete.wait()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    # 1. Send DTMF 1
    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(received.wait(), timeout=1.0)
    received.clear()

    # 2. Send DTMF 2 (should be ignored)
    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "2",
            "Unique-ID": "test-session-uuid",
        }
    )

    # 3. Send DTMF 1 again to sync (confirming 2 was ignored)
    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(received.wait(), timeout=1.0)

    test_complete.set()
    await app.stop()
    await dialplan.stop()

    assert captured_digits == ["1", "1"]


@mark.asyncio
async def test_on_dtmf_wildcard(host, port, dialplan):
    """Test onDTMF decorator without arguments (wildcard)."""
    received = asyncio.Event()
    handler_started = asyncio.Event()
    test_complete = asyncio.Event()
    captured_digits = []

    async def handler(session: Session) -> None:
        @session.channel.onDTMF()
        async def on_any_digit(digit: str):
            captured_digits.append(digit)
            received.set()

        handler_started.set()
        await test_complete.wait()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    digits = ["1", "2", "#", "*"]

    for d in digits:
        received.clear()
        await dialplan.broadcast(
            {
                "Event-Name": "DTMF",
                "DTMF-Digit": d,
                "Unique-ID": "test-session-uuid",
            }
        )
        await asyncio.wait_for(received.wait(), timeout=1.0)

    test_complete.set()
    await app.stop()
    await dialplan.stop()

    assert captured_digits == ["1", "2", "#", "*"]


@mark.asyncio
async def test_on_dtmf_multiple_handlers(host, port, dialplan):
    """Test multiple onDTMF decorators on the same session."""
    event_1 = asyncio.Event()
    event_2 = asyncio.Event()
    handler_started = asyncio.Event()
    test_complete = asyncio.Event()
    results = {"1": 0, "2": 0}

    async def handler(session: Session) -> None:
        @session.channel.onDTMF("1")
        async def on_digit_one(digit: str):
            results["1"] += 1
            event_1.set()

        @session.channel.onDTMF("2")
        async def on_digit_two(digit: str):
            results["2"] += 1
            event_2.set()

        handler_started.set()
        await test_complete.wait()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    # Send 1
    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(event_1.wait(), timeout=1.0)
    event_1.clear()

    # Send 2
    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "2",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(event_2.wait(), timeout=1.0)
    event_2.clear()

    test_complete.set()
    await app.stop()
    await dialplan.stop()

    assert results["1"] == 1
    assert results["2"] == 1
