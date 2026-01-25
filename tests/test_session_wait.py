import asyncio
import pytest

from pytest import mark

from genesis import Outbound, Session
from genesis.exceptions import TimeoutError


@mark.asyncio
async def test_wait_dtmf_success(host, port, dialplan):
    """Test wait() method successfully receiving DTMF event."""
    event_received = asyncio.Event()
    handler_started = asyncio.Event()
    received_event = None

    async def handler(session: Session) -> None:
        nonlocal received_event
        handler_started.set()
        received_event = await session.channel.wait("DTMF", timeout=5.0)
        event_received.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(event_received.wait(), timeout=5.0)

    assert received_event is not None
    assert received_event.get("DTMF-Digit") == "1"

    await app.stop()
    await dialplan.stop()


@mark.asyncio
async def test_wait_dtmf_timeout(host, port, dialplan):
    """Test wait() method timing out when no event is received."""
    timeout_occurred = asyncio.Event()

    async def handler(session: Session) -> None:
        try:
            await session.channel.wait("DTMF", timeout=0.5)
        except TimeoutError:
            timeout_occurred.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)

    await asyncio.wait_for(timeout_occurred.wait(), timeout=2.0)

    await app.stop()
    await dialplan.stop()


@mark.asyncio
async def test_wait_with_on_dtmf_handler(host, port, dialplan):
    """Test wait() works correctly with onDTMF() handlers."""
    handler_called = asyncio.Event()
    wait_completed = asyncio.Event()
    handler_started = asyncio.Event()
    received_digit = None
    received_event = None

    async def handler(session: Session) -> None:
        nonlocal received_digit, received_event

        @session.channel.onDTMF("1")
        async def on_digit_one(digit: str):
            nonlocal received_digit
            received_digit = digit
            handler_called.set()

        handler_started.set()
        received_event = await session.channel.wait("DTMF", timeout=5.0)
        wait_completed.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(wait_completed.wait(), timeout=5.0)
    await handler_called.wait()

    assert received_event is not None
    assert received_event.get("DTMF-Digit") == "1"
    assert received_digit == "1"

    await app.stop()
    await dialplan.stop()


@mark.asyncio
async def test_wait_multiple_handlers(host, port, dialplan):
    """Test wait() with multiple onDTMF handlers."""
    handler1_called = asyncio.Event()
    handler2_called = asyncio.Event()
    wait_completed = asyncio.Event()
    handler_started = asyncio.Event()
    received_event = None

    async def handler(session: Session) -> None:
        nonlocal received_event

        @session.channel.onDTMF("1")
        async def option1(digit: str):
            handler1_called.set()

        @session.channel.onDTMF("2")
        async def option2(digit: str):
            handler2_called.set()

        handler_started.set()
        received_event = await session.channel.wait("DTMF", timeout=5.0)
        wait_completed.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    # Wait for connection to be established
    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    # Wait for handler to start executing
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    await dialplan.broadcast(
        {
            "Event-Name": "DTMF",
            "DTMF-Digit": "1",
            "Unique-ID": "test-session-uuid",
        }
    )
    await asyncio.wait_for(wait_completed.wait(), timeout=5.0)
    await handler1_called.wait()

    assert received_event is not None
    assert received_event.get("DTMF-Digit") == "1"
    assert handler1_called.is_set()
    assert not handler2_called.is_set()

    await app.stop()
    await dialplan.stop()
