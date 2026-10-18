"""Consumer subscription scenarios against the loopback ESL simulator."""

import asyncio
from pathlib import Path
from typing import Any, Dict, Sequence, Tuple

from pytest_bdd import scenarios, then, when

from genesis import Consumer

from tests.bdd.world import World

FEATURE = Path(__file__).resolve().parents[1] / "features" / "consumer.feature"
scenarios(str(FEATURE))

Header = Tuple[str, str]

JOB_UUID = "7f4db78a-17d7-11dd-b7a0-db4edd065621"
JOB_BODY = "+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621\n"
JOB_ARGUMENT = "sofia/default/1005 '&park'"
AUDIO_BODY = (
    '{"audioDataType":"raw","sampleRate":16000,'
    '"file":"/tmp/84e7dad0-dc1e-4234-8c56-5688e2069d99_0.tmp.r16"}'
)


async def _finish(app: Consumer, task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if app.protocol.is_connected:
        await app.stop()


async def _deliver(
    world: World,
    event_name: str,
    headers: Sequence[Header],
    *,
    body: bytes = b"",
    filter_header: str,
    filter_value: str,
) -> Dict[str, Any]:
    received: asyncio.Queue[Any] = asyncio.Queue()
    app = Consumer(world.server.host, world.server.port, world.server.password)

    @app.handle(event_name)
    async def handler(event: Any) -> None:
        await received.put(event)

    task = asyncio.create_task(app.start())
    try:
        reply = "+OK filter added. [%s]=[%s]" % (filter_header, filter_value)
        waiter = world.journal.register_event_wait(
            lambda item, reply=reply: item.frame.header("Reply-Text") == reply
        )
        await waiter.wait(2)
        await world.server.emit(headers, body=body)
        event = await asyncio.wait_for(received.get(), 2)
        return {
            "event_name": event.get("Event-Name"),
            "subclass": event.get("Event-Subclass"),
            "body": event.body,
            "job_command": event.get("Job-Command"),
            "job_arg": event.get("Job-Command-Arg"),
            "job_uuid": event.get("Job-UUID"),
            "commands": [item.text for item in world.journal.commands()],
        }
    finally:
        await _finish(app, task)


def _commands(story: World) -> Sequence[str]:
    commands = story.facts["commands"]
    assert isinstance(commands, list)
    return commands


@when("a consumer handles HEARTBEAT", target_fixture="story")
def heartbeat(world: World) -> World:
    async def _body() -> World:
        world.facts.update(
            await _deliver(
                world,
                "HEARTBEAT",
                (("Event-Name", "HEARTBEAT"),),
                filter_header="Event-Name",
                filter_value="HEARTBEAT",
            )
        )
        return world

    return world.run(_body())


@then("the heartbeat handler ran")
def heartbeat_ran(story: World) -> None:
    assert story.facts["event_name"] == "HEARTBEAT"


@then("the journal shows the HEARTBEAT filter")
def heartbeat_filter(story: World) -> None:
    commands = _commands(story)
    assert "events plain ALL" in commands
    assert "filter Event-Name HEARTBEAT" in commands


@when("a consumer handles the custom subclass sofia register", target_fixture="story")
def sofia_register(world: World) -> World:
    async def _body() -> World:
        world.facts.update(
            await _deliver(
                world,
                "sofia::register",
                (
                    ("Event-Subclass", "sofia::register"),
                    ("Event-Name", "CUSTOM"),
                ),
                filter_header="Event-Subclass",
                filter_value="sofia::register",
            )
        )
        return world

    return world.run(_body())


@then("the handler received subclass sofia::register")
def sofia_received(story: World) -> None:
    assert story.facts["event_name"] == "CUSTOM"
    assert story.facts["subclass"] == "sofia::register"


@then("the journal shows the subclass filter for sofia::register")
def sofia_filter(story: World) -> None:
    commands = _commands(story)
    assert "events plain ALL" in commands
    assert "filter Event-Subclass sofia::register" in commands


@when("a consumer handles BACKGROUND_JOB", target_fixture="story")
def background_job(world: World) -> World:
    async def _body() -> World:
        world.facts.update(
            await _deliver(
                world,
                "BACKGROUND_JOB",
                (
                    ("Event-Name", "BACKGROUND_JOB"),
                    ("Job-Command", "originate"),
                    ("Job-Command-Arg", JOB_ARGUMENT),
                    ("Job-UUID", JOB_UUID),
                ),
                body=JOB_BODY.encode("utf-8"),
                filter_header="Event-Name",
                filter_value="BACKGROUND_JOB",
            )
        )
        return world

    return world.run(_body())


@then("the handler received the originate job result")
def job_received(story: World) -> None:
    assert story.facts["event_name"] == "BACKGROUND_JOB"
    assert story.facts["job_command"] == "originate"
    assert story.facts["job_arg"] == JOB_ARGUMENT
    assert story.facts["job_uuid"] == JOB_UUID
    assert story.facts["body"] == JOB_BODY


@then("the journal shows the BACKGROUND_JOB filter")
def job_filter(story: World) -> None:
    commands = _commands(story)
    assert "events plain ALL" in commands
    assert "filter Event-Name BACKGROUND_JOB" in commands


@when(
    "a consumer handles the custom subclass mod audio stream play",
    target_fixture="story",
)
def audio_stream(world: World) -> World:
    async def _body() -> World:
        world.facts.update(
            await _deliver(
                world,
                "mod_audio_stream::play",
                (
                    ("Event-Subclass", "mod_audio_stream::play"),
                    ("Event-Name", "CUSTOM"),
                ),
                body=AUDIO_BODY.encode("utf-8"),
                filter_header="Event-Subclass",
                filter_value="mod_audio_stream::play",
            )
        )
        return world

    return world.run(_body())


@then("the handler received the audio stream play body")
def audio_received(story: World) -> None:
    assert story.facts["event_name"] == "CUSTOM"
    assert story.facts["subclass"] == "mod_audio_stream::play"
    assert story.facts["body"] == AUDIO_BODY


@then("the journal shows the subclass filter for mod_audio_stream::play")
def audio_filter(story: World) -> None:
    commands = _commands(story)
    assert "events plain ALL" in commands
    assert "filter Event-Subclass mod_audio_stream::play" in commands
