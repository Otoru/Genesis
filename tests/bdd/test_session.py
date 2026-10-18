"""Session and outbound scenarios against an explicit full ESL peer."""

import asyncio
from pathlib import Path
from typing import Any, List

from pytest_bdd import scenarios, then, when

from genesis import Outbound, Session
from genesis.channel import Channel

from tests.bdd.world import World
from tests.simulator.connection import PendingExecution

FEATURE = Path(__file__).resolve().parents[1] / "features" / "session.feature"
scenarios(str(FEATURE))


async def _stop(world: World) -> None:
    app = world.facts.get("app")
    if app is not None:
        await app.stop()
        world.facts["app"] = None


async def _connect(
    world: World,
    handler: Any,
    *,
    events: bool = True,
    linger: bool = True,
) -> str:
    app = Outbound(handler, "127.0.0.1", 0, events=events, linger=linger)
    await app.start(block=False)
    server = app.server
    sockets = server.sockets if server is not None else None
    if not sockets:
        await app.stop()
        raise RuntimeError("outbound server did not bind")
    port = int(sockets[0].getsockname()[1])
    connection_id = await world.server.connect_dialplan("127.0.0.1", port, full=True)
    world.facts["app"] = app
    world.facts["connection_id"] = connection_id
    return connection_id


def _session_uuid(world: World) -> str:
    connection = world.server.connection(world.facts["connection_id"])
    if not connection.session_uuid:
        raise RuntimeError("outbound peer has no session uuid")
    return connection.session_uuid


async def _emit_dtmf(world: World, digit: str) -> None:
    await world.server.emit(
        (
            ("Event-Name", "DTMF"),
            ("DTMF-Digit", digit),
            ("Unique-ID", _session_uuid(world)),
        )
    )


class _ExecuteDriver:
    """Completes recorded executes and tells the handler when those writes finished.

    The handler must stay connected until ``wait_completed`` returns. Closing
    earlier races ``drain`` on Python 3.10.
    """

    def __init__(self) -> None:
        self.completed = 0
        self._pulse = asyncio.Event()

    async def run(self, world: World, stop: asyncio.Event) -> None:
        while not stop.is_set():
            waiter = asyncio.create_task(world.server.next_execution())
            halted = asyncio.create_task(stop.wait())
            _done, pending_tasks = await asyncio.wait(
                {waiter, halted}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending_tasks:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if waiter not in _done:
                return
            pending_exec = waiter.result()
            await world.server.start_execution(pending_exec)
            await world.server.complete_execution(pending_exec)
            self.completed += 1
            self._pulse.set()

    async def wait_completed(self, count: int) -> None:
        while self.completed < count:
            self._pulse.clear()
            if self.completed >= count:
                return
            await self._pulse.wait()


def _commands(world: World) -> List[str]:
    return [item.text for item in world.journal.commands(world.facts["connection_id"])]


async def _stop_driver(driver: asyncio.Task[None], stop: asyncio.Event) -> None:
    stop.set()
    if driver.done():
        await driver
        return
    driver.cancel()
    try:
        await driver
    except asyncio.CancelledError:
        pass


@when("a session listens for DTMF digit 1", target_fixture="story")
def specific_digit(world: World) -> World:
    async def _body() -> World:
        digits: List[str] = []
        received = asyncio.Event()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)

            @channel.on_dtmf("1")
            async def on_digit(digit: str) -> None:
                digits.append(digit)
                received.set()

            started.set()
            await finished.wait()

        try:
            await _connect(world, handler)
            await started.wait()
            await _emit_dtmf(world, "1")
            await received.wait()
            received.clear()
            await _emit_dtmf(world, "2")
            await _emit_dtmf(world, "1")
            await received.wait()
            world.facts["digits"] = list(digits)
        finally:
            finished.set()
            await _stop(world)
        return world

    return world.run(_body())


@then("only that digit was delivered")
def only_digit_one(story: World) -> None:
    assert story.facts["digits"] == ["1", "1"]


@when("a session listens for every DTMF digit", target_fixture="story")
def wildcard_dtmf(world: World) -> World:
    async def _body() -> World:
        digits: List[str] = []
        received = asyncio.Event()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)

            @channel.on_dtmf()
            async def on_any(digit: str) -> None:
                digits.append(digit)
                received.set()

            started.set()
            await finished.wait()

        try:
            await _connect(world, handler)
            await started.wait()
            for digit in ("1", "2", "#", "*"):
                received.clear()
                await _emit_dtmf(world, digit)
                await received.wait()
            world.facts["digits"] = list(digits)
        finally:
            finished.set()
            await _stop(world)
        return world

    return world.run(_body())


@then("every DTMF digit was delivered")
def every_digit(story: World) -> None:
    assert story.facts["digits"] == ["1", "2", "#", "*"]


@when("a session has handlers for DTMF digits 1 and 2", target_fixture="story")
def several_handlers(world: World) -> World:
    async def _body() -> World:
        counts = {"1": 0, "2": 0}
        one = asyncio.Event()
        two = asyncio.Event()
        started = asyncio.Event()
        finished = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)

            @channel.on_dtmf("1")
            async def on_one(digit: str) -> None:
                del digit
                counts["1"] += 1
                one.set()

            @channel.on_dtmf("2")
            async def on_two(digit: str) -> None:
                del digit
                counts["2"] += 1
                two.set()

            started.set()
            await finished.wait()

        try:
            await _connect(world, handler)
            await started.wait()
            await _emit_dtmf(world, "1")
            await one.wait()
            await _emit_dtmf(world, "2")
            await two.wait()
            world.facts["counts"] = dict(counts)
        finally:
            finished.set()
            await _stop(world)
        return world

    return world.run(_body())


@then("each DTMF handler ran once")
def each_handler_once(story: World) -> None:
    assert story.facts["counts"] == {"1": 1, "2": 1}


@when("a session waits for a DTMF event", target_fixture="story")
def wait_returns(world: World) -> World:
    async def _body() -> World:
        registered = asyncio.Event()
        done = asyncio.Event()

        async def handler(session: Session) -> None:
            original = session.on

            def on(key: str, fn: Any) -> None:
                original(key, fn)
                if key == "DTMF":
                    registered.set()

            session.on = on  # type: ignore[method-assign]
            world.facts["event"] = await session.channel.wait("DTMF", timeout=5)
            done.set()

        try:
            await _connect(world, handler)
            await registered.wait()
            await _emit_dtmf(world, "1")
            await done.wait()
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the wait returned digit 1")
def wait_digit(story: World) -> None:
    event = story.facts["event"]
    assert event is not None
    assert event.get("DTMF-Digit") == "1"


@when("a session waits for DTMF and no digit is emitted", target_fixture="story")
def wait_times_out(world: World) -> World:
    async def _body() -> World:
        from genesis.exceptions import TimeoutError

        timed = asyncio.Event()

        async def handler(session: Session) -> None:
            try:
                await session.channel.wait("DTMF", timeout=0.2)
            except TimeoutError:
                world.facts["timed_out"] = True
                timed.set()

        try:
            await _connect(world, handler)
            await timed.wait()
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the DTMF wait timed out")
def dtmf_timed_out(story: World) -> None:
    assert story.facts.get("timed_out") is True


@when("a session waits for DTMF and also handles digit 1", target_fixture="story")
def wait_and_handler(world: World) -> World:
    async def _body() -> World:
        registered = asyncio.Event()
        handled = asyncio.Event()
        done = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)

            @channel.on_dtmf("1")
            async def on_digit(digit: str) -> None:
                world.facts["digit"] = digit
                handled.set()

            original = session.on

            def on(key: str, fn: Any) -> None:
                original(key, fn)
                if key == "DTMF":
                    registered.set()

            session.on = on  # type: ignore[method-assign]
            world.facts["event"] = await channel.wait("DTMF", timeout=5)
            done.set()

        try:
            await _connect(world, handler)
            await registered.wait()
            await _emit_dtmf(world, "1")
            await done.wait()
            await handled.wait()
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the wait and the digit handler both saw 1")
def both_saw_digit(story: World) -> None:
    assert story.facts["event"].get("DTMF-Digit") == "1"
    assert story.facts["digit"] == "1"


@when(
    "a session waits for DTMF with handlers for 1 and 2 and digit 1 arrives",
    target_fixture="story",
)
def wait_several(world: World) -> World:
    async def _body() -> World:
        registered = asyncio.Event()
        one = asyncio.Event()
        two = asyncio.Event()
        done = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)

            @channel.on_dtmf("1")
            async def on_one(digit: str) -> None:
                del digit
                one.set()

            @channel.on_dtmf("2")
            async def on_two(digit: str) -> None:
                del digit
                two.set()

            original = session.on

            def on(key: str, fn: Any) -> None:
                original(key, fn)
                if key == "DTMF":
                    registered.set()

            session.on = on  # type: ignore[method-assign]
            world.facts["event"] = await channel.wait("DTMF", timeout=5)
            done.set()

        try:
            await _connect(world, handler)
            await registered.wait()
            await _emit_dtmf(world, "1")
            await done.wait()
            await one.wait()
            world.facts["two"] = two.is_set()
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("only the handler for digit 1 ran")
def only_digit_one_handler(story: World) -> None:
    assert story.facts["event"].get("DTMF-Digit") == "1"
    assert story.facts["two"] is False


@when("an outbound session is connected in full mode", target_fixture="story")
def connected(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()

        async def handler(session: Session) -> None:
            world.facts["context"] = dict(session.context)
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the context has the live connect fields")
def live_context(story: World) -> None:
    context = story.facts["context"]
    assert context["Control"] == "full"
    assert context["Socket-Mode"] == "async"
    assert context["Channel-State"] == "CS_EXECUTE"
    assert context["Event-Name"] == "CHANNEL_DATA"
    assert str(context["Reply-Text"]).strip() == "+OK"
    assert context["Unique-ID"]


def _execute_commands(story: World) -> List[str]:
    commands = story.facts["commands"]
    assert isinstance(commands, list)
    return [text for text in commands if text.startswith("sendmsg")]


@when("the session answers the channel", target_fixture="story")
def answers(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)
            await channel.answer()
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
            world.facts["commands"] = _commands(world)
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("sendmsg was execute answer")
def sendmsg_answer(story: World) -> None:
    command = _execute_commands(story)[-1]
    assert "call-command: execute" in command
    assert "execute-app-name: answer" in command
    assert "Event-UUID:" in command
    assert "execute-app-arg:" not in command


@when("the session parks the channel", target_fixture="story")
def parks(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()

        async def handler(session: Session) -> None:
            assert isinstance(session.channel, Channel)
            await session.channel.park()
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
            world.facts["commands"] = _commands(world)
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("sendmsg was execute park")
def sendmsg_park(story: World) -> None:
    command = _execute_commands(story)[-1]
    assert "execute-app-name: park" in command
    assert "Event-UUID:" in command


@when("the session hangs up the channel", target_fixture="story")
def hangs_up(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()

        async def handler(session: Session) -> None:
            assert isinstance(session.channel, Channel)
            await session.channel.hangup()
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
            world.facts["commands"] = _commands(world)
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("sendmsg was execute hangup")
def sendmsg_hangup(story: World) -> None:
    command = _execute_commands(story)[-1]
    assert "execute-app-name: hangup" in command
    assert "execute-app-arg: NORMAL_CLEARING" in command


@when("the session sends several sendmsg parameter sets", target_fixture="story")
def sendmsg_parameters(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()
        stop = asyncio.Event()
        sent: List[int] = [0]
        execute_driver = _ExecuteDriver()
        driver = asyncio.create_task(execute_driver.run(world, stop))

        async def handler(session: Session) -> None:
            target = session.uuid
            assert isinstance(target, str)
            assert target
            assert target == _session_uuid(world)
            world.facts["explicit_uuid"] = target
            await session.sendmsg("execute", "playback", "test.wav", lock=True)
            sent[0] += 1
            await session.sendmsg("execute", "playback", "test.wav", uuid=target)
            sent[0] += 1
            await session.sendmsg(
                "execute", "playback", "test.wav", event_uuid="test-event-5678"
            )
            sent[0] += 1
            await session.sendmsg("execute", "playback", "test.wav", block=True)
            sent[0] += 1
            await session.sendmsg(
                "execute", "playback", "test.wav", headers={"X-Test": "value"}
            )
            sent[0] += 1
            await execute_driver.wait_completed(sent[0])
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
            world.facts["commands"] = _commands(world)
        finally:
            await _stop_driver(driver, stop)
            await _stop(world)
        return world

    return world.run(_body())


@then("each sendmsg parameter set was passed through")
def sendmsg_cases(story: World) -> None:
    commands = _execute_commands(story)
    explicit = story.facts["explicit_uuid"]
    assert isinstance(explicit, str)
    assert explicit
    assert any("event-lock: true" in command for command in commands)
    assert any(command.startswith("sendmsg %s" % explicit) for command in commands)
    assert any("Event-UUID: test-event-5678" in command for command in commands)
    assert any("X-Test: value" in command for command in commands)
    assert all("execute-app-name: playback" in command for command in commands)
    assert all("execute-app-arg: test.wav" in command for command in commands)


@when(
    "an outbound handler asks for events and linger on a full peer",
    target_fixture="story",
)
def handler_options(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()

        async def handler(session: Session) -> None:
            del session
            ready.set()

        try:
            connection_id = await _connect(world, handler, events=True, linger=True)
            await ready.wait()
            world.facts["commands"] = [
                item.text for item in world.journal.commands(connection_id)
            ]
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the journal shows filter and event plain all")
def journal_filter(story: World) -> None:
    commands = story.facts["commands"]
    assert "connect" in commands
    assert "event plain all" in commands
    assert "linger" in commands
    assert "myevents" not in commands
    assert any(item.startswith("filter Unique-ID ") for item in commands)


@when(
    "the session uses log playback say and play_and_get_digits",
    target_fixture="story",
)
def helpers(world: World) -> World:
    async def _body() -> World:
        ready = asyncio.Event()
        stop = asyncio.Event()
        sent: List[int] = [0]
        execute_driver = _ExecuteDriver()
        driver = asyncio.create_task(execute_driver.run(world, stop))

        async def handler(session: Session) -> None:
            channel = session.channel
            assert isinstance(channel, Channel)
            await channel.log("INFO", "test message")
            sent[0] += 1
            await channel.playback("file.wav")
            sent[0] += 1
            await channel.say("123", kind="NUMBER", method="pronounced")
            sent[0] += 1
            await channel.play_and_get_digits(
                tries=3,
                timeout=5000,
                terminators="#",
                file="prompt.wav",
                minimal=1,
                maximum=4,
                var_name="my_digits",
                regexp="\\d+",
                digit_timeout=2000,
            )
            sent[0] += 1
            await execute_driver.wait_completed(sent[0])
            ready.set()

        try:
            await _connect(world, handler)
            await ready.wait()
            world.facts["commands"] = _commands(world)
        finally:
            await _stop_driver(driver, stop)
            await _stop(world)
        return world

    return world.run(_body())


@then("those helper applications were requested")
def helper_calls(story: World) -> None:
    commands = _execute_commands(story)
    assert any("execute-app-name: log" in command for command in commands)
    assert any("execute-app-arg: INFO test message" in command for command in commands)
    assert any(
        "execute-app-name: playback" in command and "file.wav" in command
        for command in commands
    )
    assert any("execute-app-name: say" in command for command in commands)
    assert any("en NUMBER pronounced FEMININE 123" in command for command in commands)
    assert any(
        "execute-app-name: play_and_get_digits" in command for command in commands
    )
    assert any(
        "prompt.wav" in command and "my_digits" in command for command in commands
    )


@when(
    "a blocking playback completes with the same Application-UUID",
    target_fixture="story",
)
def blocking_completes(world: World) -> World:
    async def _body() -> World:
        done = asyncio.Event()

        async def complete() -> None:
            pending = await world.server.next_execution(2)
            world.facts["event_uuid"] = pending.event_uuid
            await world.server.start_execution(pending)
            await world.server.complete_execution(pending)

        watcher = asyncio.create_task(complete())

        async def handler(session: Session) -> None:
            assert isinstance(session.channel, Channel)
            world.facts["event"] = await session.channel.playback(
                "blocking.wav", block=True
            )
            done.set()

        try:
            await _connect(world, handler)
            await done.wait()
            await watcher
        finally:
            if not watcher.done():
                watcher.cancel()
                try:
                    await watcher
                except asyncio.CancelledError:
                    pass
            await _stop(world)
        return world

    return world.run(_body())


@then("the playback result is that execute complete event")
def playback_completed(story: World) -> None:
    event = story.facts["event"]
    assert event.get("Event-Name") == "CHANNEL_EXECUTE_COMPLETE"
    assert event.get("Application-UUID") == story.facts["event_uuid"]
    assert event.get("Application-UUID") != "00000000-0000-0000-0000-000000000000"


@when(
    "a blocking playback is given a short timeout and no complete event",
    target_fixture="story",
)
def blocking_times_out(world: World) -> World:
    async def _body() -> World:
        timed = asyncio.Event()

        async def handler(session: Session) -> None:
            assert isinstance(session.channel, Channel)
            try:
                await session.channel.playback("timeout.wav", block=True, timeout=0.001)
            except asyncio.TimeoutError:
                world.facts["timed_out"] = True
                timed.set()

        try:
            await _connect(world, handler)
            await timed.wait()
            pending: PendingExecution = await world.server.next_execution(2)
            command = [
                item.text
                for item in world.journal.commands(world.facts["connection_id"])
                if "timeout.wav" in item.text
            ][-1]
            world.facts["pending_uuid"] = pending.event_uuid
            world.facts["command_has_uuid"] = (
                "Event-UUID: %s" % pending.event_uuid
            ) in command
            world.facts["completed"] = any(
                item.frame.body.find(b"CHANNEL_EXECUTE_COMPLETE") >= 0
                for item in world.journal.events(world.facts["connection_id"])
            )
        finally:
            await _stop(world)
        return world

    return world.run(_body())


@then("the blocking playback timed out")
def blocking_timeout(story: World) -> None:
    assert story.facts.get("timed_out") is True
    assert story.facts["command_has_uuid"] is True
    assert story.facts["completed"] is False
    assert story.facts["pending_uuid"]
