import asyncio

try:
    from unittest.mock import AsyncMock, PropertyMock
except ImportError:
    from mock import AsyncMock, PropertyMock

import pytest

from genesis import filtrate, Consumer

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


@pytest.mark.parametrize("content", cases)
@pytest.mark.filterwarnings("ignore: coroutine")
async def test_decorator_behavior(content):
    """Validates decorator behavior."""
    handler = AsyncMock()

    event = content["event"]
    expected = content["expected"]
    parameters = content["decorator"]

    decorator = filtrate(*parameters)
    assert callable(decorator), "The decorator result did not return a function"

    new_handler = decorator(handler)
    assert asyncio.iscoroutinefunction(
        new_handler
    ), "New handler is not a coroutine funcion"

    await new_handler(event)

    assert handler.called == expected, "The handler has stored the expected value"


async def test_decorator_not_change_behavior_of_funcion():
    app = Consumer("127.0.0.1", 8021, "ClueCon")

    @app.handle("sofia::register")
    async def handle(event):
        await asyncio.sleep(0.0001)
        return "result"

    expected = "result"
    got = await handle(dict())

    assert got == expected, "The result of the function is not as expected"


async def test_consumer_with_heartbeat_event(freeswitch, heartbeat):
    async with freeswitch as server:
        server.events.append(heartbeat)
        server.oncommand(
            "filter Event-Name HEARTBEAT",
            "+OK filter added. [filter]=[Event-Name HEARTBEAT]",
        )

        semaphore = asyncio.Event()

        async def effect(*args, **kwargs):
            semaphore.set()

        handler = AsyncMock(side_effect=effect)
        app = Consumer(*freeswitch.address)
        app.handle("HEARTBEAT")(handler)

        future = asyncio.create_task(app.start())
        await semaphore.wait()

        await app.stop()
        future.cancel()

    assert handler.called, "The handler has stored the expected value"


async def test_consumer_with_register_custom_event(freeswitch, register):
    async with freeswitch as server:
        server.events.append(register)
        server.oncommand(
            "filter Event-Subclass sofia::register",
            "+OK filter added. [filter]=[Event-Subclass sofia::register]",
        )

        semaphore = asyncio.Event()

        async def effect(*args, **kwargs):
            semaphore.set()

        handler = AsyncMock(side_effect=effect)
        app = Consumer(*freeswitch.address)
        app.handle("sofia::register")(handler)

        future = asyncio.create_task(app.start())
        await semaphore.wait()

        await app.stop()
        future.cancel()

    assert handler.called, "The handler has stored the expected value"


async def test_consumer_wait_method_is_callend(freeswitch):
    semaphore = asyncio.Event()

    async with freeswitch as server:
        spider = AsyncMock(side_effect=semaphore.set)
        app = Consumer(*server.address)
        app.wait = spider

        future = asyncio.ensure_future(app.start())
        await semaphore.wait()

        assert spider.called, "the wait method was called successfully"

        await app.stop()
        future.cancel()


async def test_consumer_wait_method_behavior(host, port, password, monkeypatch):
    spider = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", spider)

    address = (host(), port(), password())
    app = Consumer(*address)

    app.protocol.is_connected = PropertyMock()
    app.protocol.is_connected.side_effect = [True, True, False]
    app.protocol.is_connected.__bool__ = lambda self: self()

    await app.wait()

    message = "The consumer stopped when the connection was closed."
    assert spider.call_count == 2, message


async def test_recive_background_job_event(freeswitch, background_job):
    async with freeswitch as server:
        server.events.append(background_job)
        server.oncommand(
            "filter Event-Name BACKGROUND_JOB",
            "+OK filter added. [filter]=[Event-Name BACKGROUND_JOB]",
        )

        buffer = asyncio.Queue()
        app = Consumer(*server.address)

        @app.handle("BACKGROUND_JOB")
        async def handler(event):
            await buffer.put(event)

        future = asyncio.ensure_future(app.start())
        event = await buffer.get()

        assert event == {
            "Content-Type": "text/event-plain",
            "Core-UUID": "42bdf272-16e6-11dd-b7a0-db4edd065621",
            "Event-Date-GMT": "Thu, 01 May 2008 23:37:03 GMT",
            "Event-Date-Local": "2008-05-02 07:37:03",
            "Event-Date-timestamp": "1209685023894968",
            "Event-Name": "BACKGROUND_JOB",
            "FreeSWITCH-Hostname": "ser",
            "FreeSWITCH-IPv4": "192.168.1.104",
            "FreeSWITCH-IPv6": "127.0.0.1",
            "Job-Command": "originate",
            "Job-Command-Arg": "sofia/default/1005 '&park'",
            "Job-UUID": "7f4db78a-17d7-11dd-b7a0-db4edd065621",
            "Event-Calling-File": "mod_event_socket.c",
            "Event-Calling-Function": "api_exec",
            "Event-Calling-Line-Number": "609",
            "Content-Length": "40",
        }, "The header parsing did not go as expected."

        assert (
            event.body == "+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621"
        ), "The body parsing did not go as expected."

        await app.stop()
        future.cancel()
