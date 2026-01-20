from __future__ import annotations

from asyncio import get_event_loop_policy
from typing import AsyncGenerator, Awaitable, Callable, Dict

import pytest

from tests import payloads
from tests.doubles import Dialplan, Freeswitch, get_free_tcp_port, get_random_password


@pytest.fixture
def mod_audio_stream_play() -> str:
    return payloads.mod_audio_stream_play


@pytest.fixture
def heartbeat() -> str:
    return payloads.heartbeat


@pytest.fixture
def channel() -> Dict[str, str]:
    events = dict()
    events["create"] = payloads.channel_create
    return events


@pytest.fixture
def background_job() -> str:
    return payloads.background_job


@pytest.fixture
def custom() -> str:
    return payloads.custom


@pytest.fixture
def register() -> str:
    return payloads.register


@pytest.fixture
def connect() -> str:
    return payloads.connect


@pytest.fixture
def generic() -> str:
    return payloads.generic


@pytest.fixture(scope="session")
def event_loop(request: pytest.FixtureRequest):
    loop = get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def host() -> Callable[[], str]:
    return lambda: "127.0.0.1"


@pytest.fixture(scope="session")
async def port() -> Callable[[], int]:
    return lambda: get_free_tcp_port()


@pytest.fixture(scope="session")
async def password() -> Callable[[], str]:
    return lambda: get_random_password(7)


@pytest.fixture()
async def freeswitch(event_loop, port, password) -> AsyncGenerator[Freeswitch, None]:
    server = Freeswitch("127.0.0.1", 0, password())
    async with server:
        yield server


@pytest.fixture
async def dialplan(connect, generic) -> Dialplan:
    instance = Dialplan()
    instance.oncommand("linger", generic)
    instance.oncommand("connect", connect)
    instance.oncommand("myevents", generic)

    return instance
