import pytest
import asyncio
from textwrap import dedent

from genesis.exceptions import AuthenticationError
from genesis import Inbound

from environment import Freeswitch, Callback, EVENTS


@pytest.mark.asyncio
async def test_connect_without_freeswitch():
    with pytest.raises(ConnectionRefusedError):
        async with Inbound("0.0.0.0", 8021, "ClueCon"):
            await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_connect_with_freesswitch():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("uptime")
            message = "The answer is not what we expected"
            assert response["Reply-Text"] == "6943047", message


@pytest.mark.asyncio
async def test_connect_without_freeswitch_and_wrong_password():
    with pytest.raises(AuthenticationError):
        async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
            async with Inbound("0.0.0.0", 8021, "WrongPassword"):
                await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_send_api_command():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("api console loglevel")
            message = "The answer is not what we expected"
            expected = "+OK console log level set to DEBUG"
            assert response["X-API-Reply-Text"] == expected, message


@pytest.mark.asyncio
async def test_send_api_command_with_large_reponse():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("api status")
            message = "The answer is not what we expected"
            expected = """UP 0 years, 80 days, 8 hours, 25 minutes, 5 seconds, 869 milliseconds, 87 microseconds
FreeSWITCH (Version 1.10.3-release git e52b1a8 2020-09-09 12:16:24Z 64bit) is ready
7653 session(s) since startup
0 session(s) - peak 2, last 5min 0
0 session(s) per Sec out of max 30, peak 14, last 5min 0
1000 session(s) max
min idle cpu 0.00/99.00
Current Stack Size/Max 240K/8192K"""
            assert response["X-API-Reply-Text"] == expected, message


@pytest.mark.asyncio
async def test_event_handler_on_inbound_client():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    events = [EVENTS["HEARTBEAT"]]

    async with Freeswitch("0.0.0.0", 8021, "ClueCon", events):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("HEARTBEAT", handler)
            await asyncio.sleep(0.001)

    assert handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_wildcard_handler_on_inbound_client():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    events = [EVENTS["HEARTBEAT"]]

    async with Freeswitch("0.0.0.0", 8021, "ClueCon", events):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("*", handler)
            await asyncio.sleep(0.001)

    assert handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_event_handler_not_is_called_with_wrong_event():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    events = [EVENTS["HEARTBEAT"]]

    async with Freeswitch("0.0.0.0", 8021, "ClueCon", events):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("MESSAGE", handler)
            await asyncio.sleep(0.001)

    assert not handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_event_handler_is_called_with_all_events():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    events = [
        EVENTS["MESSAGE"],
        EVENTS["MESSAGE"],
        EVENTS["MESSAGE"],
        EVENTS["MESSAGE"],
    ]

    async with Freeswitch("0.0.0.0", 8021, "ClueCon", events):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("MESSAGE", handler)
            await asyncio.sleep(0.001)

    assert not handler.count == len(events), "Event processing did not activate handler"