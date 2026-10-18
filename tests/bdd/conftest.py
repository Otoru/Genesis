import asyncio
from typing import Iterator

import pytest

from tests.bdd.world import World
from tests.simulator.server import Simulator


async def _open_simulator() -> Simulator:
    simulator = Simulator("lab-password")
    await simulator.start()
    return simulator


async def _shutdown(server: Simulator) -> None:
    await server.close()
    current = asyncio.current_task()
    leftover = [
        task for task in asyncio.all_tasks() if task is not current and not task.done()
    ]
    for task in leftover:
        task.cancel()
    if leftover:
        await asyncio.gather(*leftover, return_exceptions=True)
    await asyncio.get_running_loop().shutdown_asyncgens()


@pytest.fixture
def world() -> Iterator[World]:
    """One simulator bound to the loop the sync BDD steps will drive."""
    loop = asyncio.new_event_loop()
    try:
        server = loop.run_until_complete(_open_simulator())
        bundle = World(server, loop)
        try:
            yield bundle
        finally:
            loop.run_until_complete(_shutdown(server))
    finally:
        loop.close()
