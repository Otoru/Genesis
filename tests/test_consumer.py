from inspect import iscoroutinefunction
import asyncio

import pytest

from genesis import filtrate, Consumer

from environment import Callback, Freeswitch, EVENTS


cases = [
    {"decorator": ["key"], "expected": True, "event": {"key": "value"}},
    {"decorator": ["key"], "expected": False, "event": {"invalid_key": "value"}},
    {"decorator": ["key", "value"], "expected": True, "event": {"key": "value"}},
    {
        "decorator": ["key", "value"],
        "expected": False,
        "event": {"key": "another_value"},
    },
    {
        "decorator": ["key", "^[a-z]{5}$", True],
        "expected": True,
        "event": {"key": "value"},
    },
    {
        "decorator": ["key", "^[a-z]{3}$", True],
        "expected": False,
        "event": {"key": "value"},
    },
]


def test_filtrate_is_a_callable():
    """Verify if 'filtrate' is a callable."""
    assert callable(filtrate)


def test_filtrate_require_a_single_argument():
    """Verify if 'filtrate' is a callable."""
    msg = "filtrate() missing 1 required positional argument: 'key'"
    with pytest.raises(TypeError) as exc:
        filtrate()  # pylint: disable=no-value-for-parameter
        assert msg in str(exc)


@pytest.mark.asyncio
async def test_decorator_not_change_behavior_of_funcion():
    app = Consumer("127.0.0.1", 8021, "ClueCon")

    @app.handle("sofia::register")
    async def handle(event):
        await asyncio.sleep(0.0001)
        return "result"

    expected = "result"
    got = await handle(dict())

    assert got == expected, "The result of the function is not as expected"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", cases)
async def test_decorator_behavior(content):
    """Validates decorator behavior."""
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    event = content["event"]
    expected = content["expected"]
    parameters = content["decorator"]

    decorator = filtrate(*parameters)
    assert callable(decorator), "The decorator result did not return a function"

    new_handler = decorator(handler)
    assert iscoroutinefunction(new_handler), "New handler is not a coroutine funcion"
    await new_handler(event)

    assert handler.is_called == expected, "The handler has stored the expected value"


@pytest.mark.asyncio
async def test_conmsumer_store_handlers_on_protocol():
    """Ensures that handlers are passed to the protocol."""
    app = Consumer("127.0.0.1", 8021, "ClueCon")

    async def handler(event):
        await asyncio.sleep(0.001)

    app.handle("HEARTBEAT")(handler)

    message = "The handler was not saved in the protocol"
    assert handler in app.protocol.handlers["HEARTBEAT"], message


@pytest.mark.asyncio
async def test_consumer_handle_freeswitch_events():
    """Ensures that the handler is called upon receiving an event."""
    events = [EVENTS["CUSTOM"], EVENTS["HEARTBEAT"]]

    handler = Callback()
    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon", events):
        app = Consumer("127.0.0.1", 8021, "ClueCon")

        app.handle("HEARTBEAT")(handler)

        future = asyncio.create_task(app.start())
        await handler.sync.wait()

        await app.stop()
        future.cancel()

    assert handler.is_called, "The handler has stored the expected value"


@pytest.mark.asyncio
async def test_consumer_handle_freeswitch_custom_events():
    """Ensures that the handler is called upon receiving an event."""
    handler = Callback()
    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        app = Consumer("127.0.0.1", 8021, "ClueCon")
        server.events.extend([EVENTS["CUSTOM"], EVENTS["HEARTBEAT"]])

        app.handle("example::heartbeat")(handler)

        future = asyncio.create_task(app.start())
        await handler.sync.wait()

        await app.stop()
        future.cancel()

    assert handler.is_called, "The handler has stored the expected value"
