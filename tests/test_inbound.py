import pytest
import asyncio
from textwrap import dedent

from genesis.exceptions import (
    AuthenticationError,
    ConnectionTimeoutError,
    UnconnectedError,
    ConnectionError,
)
from genesis import Inbound

from environment import Freeswitch, Callback, EVENTS


@pytest.mark.asyncio
async def test_send_command_without_connection():
    with pytest.raises(UnconnectedError):
        client = Inbound("0.0.0.0", 8021, "ClueCon")
        await client.send("uptime")


@pytest.mark.asyncio
async def test_connect_without_freeswitch():
    with pytest.raises(ConnectionRefusedError):
        async with Inbound("0.0.0.0", 8021, "ClueCon"):
            await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_connect_with_freesswitch():
    with pytest.raises(ConnectionTimeoutError):
        async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
            async with Inbound("0.0.0.0", 8021, "ClueCon", 0) as client:
                await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_inbound_client_timeout():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("uptime")
            message = "The answer is not what we expected"
            assert response["Reply-Text"] == "6943047", message


@pytest.mark.asyncio
async def test_connect_with_freeswitch_and_wrong_password():
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
            assert response["X-Event-Content"] == expected, message


@pytest.mark.asyncio
async def test_send_api_command_with_large_reponse():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("api status")
            message = "The answer is not what we expected"
            expected = (
                "UP 0 years, 80 days, 8 hours, 25 minutes, 5 seconds, 869 milliseconds, 87 microseconds\n"
                "FreeSWITCH (Version 1.10.3-release git e52b1a8 2020-09-09 12:16:24Z 64bit) is ready\n"
                "7653 session(s) since startup\n"
                "0 session(s) - peak 2, last 5min 0\n"
                "0 session(s) per Sec out of max 30, peak 14, last 5min 0\n"
                "1000 session(s) max\n"
                "min idle cpu 0.00/99.00\n"
                "Current Stack Size/Max 240K/8192K"
            )
            assert response["X-Event-Content"] == expected, message


@pytest.mark.asyncio
async def test_event_handler_on_inbound_client():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("HEARTBEAT", handler)
            server.events.append(EVENTS["HEARTBEAT"])

            await client.send("events plain ALL")
            await handler.sync.wait()

    assert handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_custom_event_handler_on_inbound_client():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("example::heartbeat", handler)
            server.events.append(EVENTS["CUSTOM"])

            await client.send("events plain ALL")
            await handler.sync.wait()

    assert handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_wildcard_handler_on_inbound_client():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("*", handler)
            server.events.append(EVENTS["HEARTBEAT"])

            await client.send("events plain ALL")
            await handler.sync.wait()

    assert handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_event_handler_not_is_called_with_wrong_event():
    handler = Callback()

    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("MESSAGE", handler)
            server.events.append(EVENTS["HEARTBEAT"])

            await asyncio.sleep(0.001)

    assert not handler.is_called, "Event processing did not activate handler"


@pytest.mark.asyncio
async def test_to_remove_event_handler():
    handler = Callback()

    client = Inbound("0.0.0.0", 8021, "ClueCon")
    client.on("MESSAGE", handler)

    assert handler in client.handlers["MESSAGE"], "The handler has not been registered"

    client.remove("MESSAGE", handler)

    assert handler not in client.handlers["MESSAGE"], "The handler has not been removed"


@pytest.mark.asyncio
async def test_event_handler_is_called_with_all_events():
    handler = Callback()
    NUMBER_OF_SENDED_EVENTS = 4

    assert not handler.is_called, "Control started with wrong value"

    async with Freeswitch("0.0.0.0", 8021, "ClueCon") as server:
        async with Inbound("0.0.0.0", 8021, "ClueCon") as client:
            client.on("MESSAGE", handler)
            server.events.extend(
                [
                    EVENTS["MESSAGE"],
                    EVENTS["MESSAGE"],
                    EVENTS["MESSAGE"],
                    EVENTS["MESSAGE"],
                ]
            )
            await asyncio.sleep(0.001)

    assert (
        not handler.count == NUMBER_OF_SENDED_EVENTS
    ), "Event processing did not activate handler"
