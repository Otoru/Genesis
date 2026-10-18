from __future__ import annotations

from typing import AsyncGenerator

import pytest

from tests.simulator.server import Simulator


@pytest.fixture
async def esl_server() -> AsyncGenerator[Simulator, None]:
    async with Simulator("lab-password") as simulator:
        yield simulator
