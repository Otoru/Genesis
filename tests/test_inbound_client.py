import pytest
import asyncio

from genesis import Client

from environment import Freeswitch


@pytest.mark.asyncio
async def test_connect_without_freeswitch():
    with pytest.raises(ConnectionRefusedError):
        async with Client("0.0.0.0", 8021, "ClueCon"):
            await asyncio.sleep(1)


@pytest.mark.asyncio
async def test_connect_with_freesswitch():
    async with Freeswitch("0.0.0.0", 8021, "ClueCon"):
        async with Client("0.0.0.0", 8021, "ClueCon") as client:
            response = await client.send("uptime")
            assert (
                response["Reply-Text"] == "6943047"
            ), "The answer is not what we expected"
