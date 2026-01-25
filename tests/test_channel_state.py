import pytest
import asyncio

from genesis import Channel, Inbound
from genesis.exceptions import ChannelError
from genesis.types import ChannelState
from tests.payloads import channel_state


async def wait_for_state(client, channel, expected_state: ChannelState, timeout=1.0):
    future: asyncio.Future[bool] = asyncio.Future()

    def check_state(event):
        try:
            if (
                event.get("Unique-ID") == channel.uuid
                and channel.state == expected_state
            ):
                if not future.done():
                    future.set_result(True)
        except Exception as e:
            if not future.done():
                future.set_exception(e)

    # Register the handler
    client.on("CHANNEL_STATE", check_state)

    try:
        # Check if already in state
        if channel.state == expected_state:
            return

        await asyncio.wait_for(future, timeout=timeout)
    finally:
        client.remove("CHANNEL_STATE", check_state)


@pytest.mark.asyncio
async def test_channel_state_update(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Initial state
            assert channel.state == ChannelState.NEW

            # Simulate CHANNEL_STATE event
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_EXECUTE",
                variable_test_key="test_value",
            )

            # Start the broadcast
            broadcast_task = asyncio.create_task(freeswitch.broadcast(event_body))

            # Wait for state update using event listener
            await wait_for_state(client, channel, ChannelState.EXECUTE)
            await broadcast_task

            assert channel.state == ChannelState.EXECUTE
            assert channel.context.get("variable_test_key") == "test_value"


@pytest.mark.asyncio
async def test_channel_state_validation_bridge(freeswitch, host, port, dialplan):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Move to DESTROY state
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_DESTROY",
                variable_test_key="test_value",
            )

            broadcast_task = asyncio.create_task(freeswitch.broadcast(event_body))
            await wait_for_state(client, channel, ChannelState.DESTROY)
            await broadcast_task

            other = await Channel.create(client, "user/2000")

            with pytest.raises(
                ChannelError, match="Cannot bridge channel in state DESTROY"
            ):
                await channel.bridge(other)


@pytest.mark.asyncio
async def test_channel_state_validation_hangup(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Move to DESTROY state
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_DESTROY",
                variable_test_key="test_value",
            )

            broadcast_task = asyncio.create_task(freeswitch.broadcast(event_body))
            await wait_for_state(client, channel, ChannelState.DESTROY)
            await broadcast_task

            # hangup() returns silently when channel is already destroyed
            await channel.hangup()


@pytest.mark.asyncio
async def test_channel_state_ordering():
    """Test that channel states are properly ordered."""
    assert ChannelState.NEW < ChannelState.EXECUTE
    assert ChannelState.EXECUTE < ChannelState.HANGUP
    assert ChannelState.HANGUP < ChannelState.DESTROY
    assert ChannelState.DESTROY > ChannelState.NEW


@pytest.mark.asyncio
async def test_channel_state_from_freeswitch():
    """Test conversion from FreeSWITCH state strings."""
    assert ChannelState.from_freeswitch("CS_NEW") == ChannelState.NEW
    assert ChannelState.from_freeswitch("CS_EXECUTE") == ChannelState.EXECUTE
    assert ChannelState.from_freeswitch("CS_DESTROY") == ChannelState.DESTROY

    # Test without prefix
    assert ChannelState.from_freeswitch("NEW") == ChannelState.NEW
