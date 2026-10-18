"""Outbound handler failure and task cleanup."""

import asyncio
from typing import List

import pytest

from genesis import Outbound

from tests.simulator.server import Simulator


async def test_handler_failure_is_recorded_and_the_task_is_dropped() -> None:
    """A handler exception is counted and the connection task does not linger."""
    entered = asyncio.Event()
    holder: List[asyncio.Task[None]] = []

    async def handler(session: object) -> None:
        del session
        task = asyncio.current_task()
        if not isinstance(task, asyncio.Task):
            raise RuntimeError("outbound handler is not a task")
        holder.append(task)
        entered.set()
        raise RuntimeError("handler failed")

    app = Outbound(handler, "127.0.0.1", 0, events=False, linger=False)
    await app.start(block=False)
    try:
        async with Simulator("lab-password") as simulator:
            sockets = app.server.sockets if app.server is not None else None
            assert sockets
            port = int(sockets[0].getsockname()[1])
            connection_id = await simulator.connect_dialplan(
                "127.0.0.1", port, full=True
            )
            await asyncio.wait_for(entered.wait(), 2)
            with pytest.raises(RuntimeError, match="handler failed"):
                await holder[0]
            assert app.tasks == set()
            commands = [item.text for item in simulator.journal.commands(connection_id)]
    finally:
        await app.stop()
    assert "connect" in commands
    assert app.tasks == set()


async def test_stop_cancels_a_handler_that_is_still_running() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(session: object) -> None:
        del session
        started.set()
        await release.wait()

    app = Outbound(handler, "127.0.0.1", 0, events=False, linger=False)
    await app.start(block=False)
    sockets = app.server.sockets if app.server is not None else None
    assert sockets
    port = int(sockets[0].getsockname()[1])
    async with Simulator("lab-password") as simulator:
        await simulator.connect_dialplan("127.0.0.1", port, full=True)
        await asyncio.wait_for(started.wait(), 2)
        task = next(iter(app.tasks))
        await app._cancel_connection_task(task)
        assert task.done()
        assert not release.is_set()
        await app.stop()
    assert app.tasks == set()
