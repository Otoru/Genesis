import asyncio
from textwrap import dedent

try:
    from unittest.mock import AsyncMock
except ImportError:
    from mock import AsyncMock

import pytest

from genesis.exceptions import (
    ConnectionTimeoutError,
    AuthenticationError,
    UnconnectedError,
    ConnectionError,
)
from genesis import Inbound


async def test_send_command_without_connection():
    with pytest.raises(UnconnectedError):
        client = Inbound("0.0.0.0", 8021, "ClueCon")
        await client.send("uptime")


async def test_connect_without_freeswitch(port):
    with pytest.raises((ConnectionRefusedError, OSError)):
        async with Inbound("0.0.0.0", port(), "ClueCon"):
            await asyncio.sleep(1)


async def test_connect_timeout_with_freesswitch(freeswitch):
    with pytest.raises(ConnectionTimeoutError):
        async with Inbound(*freeswitch.address, 0):
            await asyncio.sleep(1)


async def test_inbound_client_with_invalid_password(freeswitch):
    async with freeswitch:
        with pytest.raises(AuthenticationError):
            async with Inbound(freeswitch.host, freeswitch.port, "invalid"):
                await asyncio.sleep(1)


async def test_inbound_client_send_command(freeswitch):
    async with freeswitch as server:
        server.oncommand("uptime", "6943047")
        async with Inbound(*freeswitch.address) as client:
            response = await client.send("uptime")
            message = "The answer is not what we expected"
            assert response["Reply-Text"] == "6943047", message


async def test_send_api_command_with_large_reponse(freeswitch):
    status = dedent(
        """\
        UP 0 years, 80 days, 8 hours, 25 minutes, 5 seconds, 869 milliseconds, 87 microseconds
        FreeSWITCH (Version 1.10.3-release git e52b1a8 2020-09-09 12:16:24Z 64bit) is ready
        "7653 session(s) since startup
        0 session(s) - peak 2, last 5min 0
        0 session(s) per Sec out of max 30, peak 14, last 5min 0
        1000 session(s) max
        min idle cpu 0.00/99.00
        Current Stack Size/Max 240K/8192K"""
    )
    async with freeswitch as server:
        server.oncommand("api status", status)
        async with Inbound(*freeswitch.address) as client:
            response = await client.send("api status")
            message = "The answer is not what we expected"
            assert response.body == status, message


async def test_event_handler_on_inbound_client(freeswitch, heartbeat):
    async with freeswitch as server:
        server.events.append(heartbeat)
        async with Inbound(*freeswitch.address) as client:
            semaphore = asyncio.Event()

            async def effect(*args, **kwargs):
                semaphore.set()

            handler = AsyncMock(side_effect=effect)

            client.on("HEARTBEAT", handler)
            await client.send("events plain ALL")
            await semaphore.wait()

    assert handler.called, "Event processing did not activate handler"


async def test_custom_event_handler_on_inbound_client(freeswitch, register):
    async with freeswitch as server:
        server.events.append(register)
        async with Inbound(*freeswitch.address) as client:
            semaphore = asyncio.Event()

            async def effect(*args, **kwargs):
                semaphore.set()

            handler = AsyncMock(side_effect=effect)

            client.on("sofia::register", handler)
            await client.send("events plain ALL")
            await semaphore.wait()

    assert handler.called, "Event processing did not activate handler"


async def test_to_remove_event_handler():
    handler = AsyncMock()

    client = Inbound("0.0.0.0", 8021, "ClueCon")
    client.on("MESSAGE", handler)

    assert handler in client.handlers["MESSAGE"], "The handler has not been registered"

    client.remove("MESSAGE", handler)

    assert handler not in client.handlers["MESSAGE"], "The handler has not been removed"


async def test_inbound_client_send_command(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            with pytest.raises(ConnectionError):
                client.writer.close()
                await client.send("uptime")
