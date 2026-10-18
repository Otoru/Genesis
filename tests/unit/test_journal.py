import asyncio

import pytest

from tests.simulator.journal import Journal
from tests.simulator.codec import ESLFrame


def _frame(content_type: str) -> ESLFrame:
    return ESLFrame((("Content-Type", content_type),), b"")


async def test_command_history_is_ordered_per_connection():
    journal = Journal()
    journal.record_command("a", "auth lab")
    journal.record_command("b", "api status")
    journal.record_command("a", "events plain ALL")

    assert [item.text for item in journal.commands("a")] == [
        "auth lab",
        "events plain ALL",
    ]
    assert [item.sequence for item in journal.commands()] == [0, 1, 2]
    assert [item.text for item in journal.commands("b")] == ["api status"]


async def test_command_wait_registered_before_the_record():
    journal = Journal()
    wait = journal.register_command_wait(
        lambda command: command.connection_id == "a" and command.text == "api status"
    )
    ready = asyncio.Event()

    async def publish() -> None:
        await ready.wait()
        journal.record_command("b", "api status")
        journal.record_command("a", "api status")

    task = asyncio.create_task(publish())
    ready.set()
    seen = await wait.wait(1)
    await task
    assert seen.connection_id == "a"
    assert seen.text == "api status"
    assert seen.sequence == 1


async def test_timed_out_wait_does_not_observe_a_later_command():
    journal = Journal()
    wait = journal.register_command_wait(lambda command: command.text == "exit")
    with pytest.raises(asyncio.TimeoutError):
        await wait.wait(0)
    journal.record_command("a", "exit")
    with pytest.raises(asyncio.TimeoutError):
        await wait.wait(0)
    fresh = journal.register_command_wait(lambda command: command.text == "exit")
    seen = await fresh.wait(0)
    assert seen.text == "exit"
    assert seen.sequence == 0


async def _next_turn() -> None:
    future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().call_soon(future.set_result, None)
    await future


async def test_cancelled_wait_leaves_the_later_command_for_a_new_wait():
    journal = Journal()
    wait = journal.register_command_wait(lambda command: command.text == "exit")
    task = asyncio.create_task(wait.wait(5))
    await _next_turn()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert wait.abandoned
    journal.record_command("a", "exit")
    with pytest.raises(asyncio.TimeoutError):
        await wait.wait(0)
    fresh = journal.register_command_wait(lambda command: command.text == "exit")
    seen = await fresh.wait(0)
    assert seen.text == "exit"
    assert seen.connection_id == "a"


async def test_command_wait_matches_history_already_recorded():
    journal = Journal()
    journal.record_command("a", "exit")
    wait = journal.register_command_wait(lambda command: command.text == "exit")
    seen = await wait.wait(0)
    assert seen.text == "exit"
    assert seen.sequence == 0


async def test_command_wait_times_out_when_nothing_matches():
    journal = Journal()
    wait = journal.register_command_wait(lambda command: command.text == "exit")
    with pytest.raises(asyncio.TimeoutError):
        await wait.wait(0)


async def test_event_wait_registered_before_the_record():
    journal = Journal()
    ready = asyncio.Event()
    wait = journal.register_event_wait(
        lambda observed: observed.frame.header("Content-Type") == "text/event-plain"
    )

    async def publish() -> None:
        await ready.wait()
        journal.record_event("a", _frame("text/event-plain"))

    task = asyncio.create_task(publish())
    ready.set()
    seen = await wait.wait(1)
    await task
    assert seen.connection_id == "a"
    assert seen.frame.header("Content-Type") == "text/event-plain"
    assert [item.sequence for item in journal.events()] == [0]


async def test_event_history_stays_with_its_connection():
    journal = Journal()
    journal.record_event("a", _frame("auth/request"))
    journal.record_event("b", _frame("command/reply"))
    assert [item.frame.header("Content-Type") for item in journal.events("b")] == [
        "command/reply"
    ]
