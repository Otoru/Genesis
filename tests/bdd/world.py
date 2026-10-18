"""Per-scenario state for one simulator and its journal."""

import asyncio
from typing import Any, Awaitable, Dict

from tests.simulator.server import Simulator


class World:
    """Simulator handle, journal, and facts recorded by a scenario."""

    def __init__(self, server: Simulator, loop: asyncio.AbstractEventLoop) -> None:
        self.server = server
        self.journal = server.journal
        self.facts: Dict[str, Any] = {}
        self.loop = loop

    def run(self, coro: Awaitable[Any]) -> Any:
        """Run one scenario body on this fixture's loop.

        pytest-bdd 9 does not await an async step. The loop is the one that
        started the simulator and it is not already running.
        """
        if self.loop.is_running():
            raise RuntimeError("refusing to nest a loop that is already running")
        return self.loop.run_until_complete(coro)
