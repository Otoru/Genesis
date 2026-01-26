import asyncio

import pytest

from genesis import Inbound, RingGroup, RingMode, Channel, InMemoryLoadBalancer
from genesis.types import ChannelState
from genesis.exceptions import TimeoutError
from tests.payloads import channel_answer, channel_state


async def wait_for_channels(
    freeswitch, expected_count: int, timeout: float = 1.0
) -> list[str]:
    """Wait for channels to be created using event-based waiting."""
    start_time = asyncio.get_event_loop().time()

    channels = list(freeswitch.calls.keys())
    if len(channels) >= expected_count:
        return channels

    async with freeswitch._call_created_condition:
        while True:
            channels = list(freeswitch.calls.keys())
            if len(channels) >= expected_count:
                return channels

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                raise TimeoutError(
                    f"Expected {expected_count} channels, got {len(channels)} after {elapsed}s"
                )

            remaining_timeout = timeout - elapsed
            try:
                await asyncio.wait_for(
                    freeswitch._call_created_condition.wait(),
                    timeout=remaining_timeout,
                )
            except asyncio.TimeoutError:
                channels = list(freeswitch.calls.keys())
                if len(channels) >= expected_count:
                    return channels
                elapsed = asyncio.get_event_loop().time() - start_time
                raise TimeoutError(
                    f"Expected {expected_count} channels, got {len(channels)} after {elapsed}s"
                )


async def wait_for_state_event_processed(
    client, channel_uuid: str, state: str, timeout: float = 1.0
) -> None:
    """Wait for a CHANNEL_STATE event to be processed using event-based waiting."""
    event_processed = asyncio.Event()

    async def state_handler(event):
        if (
            event.get("Unique-ID") == channel_uuid
            and event.get("Channel-State") == state
        ):
            event_processed.set()

    client.on("CHANNEL_STATE", state_handler)
    try:
        await asyncio.wait_for(event_processed.wait(), timeout=timeout)
    finally:
        client.remove("CHANNEL_STATE", state_handler)


async def send_state_and_answer_events(
    freeswitch, client, channel_uuid: str, state: str = "CS_EXECUTE"
) -> None:
    """Send CHANNEL_STATE and CHANNEL_ANSWER events, waiting for state to be processed."""
    event_body = channel_state.format(
        unique_id=channel_uuid,
        state=state,
        variable_test_key="test_value",
    )
    await freeswitch.broadcast(event_body)
    await wait_for_state_event_processed(client, channel_uuid, state, timeout=1.0)

    answer_event = channel_answer.format(unique_id=channel_uuid)
    await freeswitch.broadcast(answer_event)


@pytest.mark.asyncio
async def test_ring_group_parallel_first_answers(freeswitch):
    """Test parallel ring mode where first callee answers."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002", "user/1003"]

            ring_task = asyncio.create_task(
                RingGroup.ring(client, group, RingMode.PARALLEL, timeout=2.0)
            )

            created_channels = await wait_for_channels(freeswitch, 3)

            second_channel_uuid = created_channels[1]
            await send_state_and_answer_events(freeswitch, client, second_channel_uuid)

            answered = await ring_task

            assert answered is not None
            assert answered.uuid == second_channel_uuid

            hangups = [uuid for uuid, _ in freeswitch.hangups]
            assert created_channels[0] in hangups
            assert created_channels[2] in hangups
            assert second_channel_uuid not in hangups


@pytest.mark.asyncio
async def test_ring_group_parallel_no_answer(freeswitch):
    """Test parallel ring mode when no one answers."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002"]

            answered = await RingGroup.ring(
                client, group, RingMode.PARALLEL, timeout=0.2
            )

            assert answered is None

            created_channels = list(freeswitch.calls.keys())
            assert len(created_channels) == 2
            hangups = [uuid for uuid, _ in freeswitch.hangups]
            assert all(uuid in hangups for uuid in created_channels)


@pytest.mark.asyncio
async def test_ring_group_sequential_first_answers(freeswitch):
    """Test sequential ring mode where first callee answers."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002", "user/1003"]

            ring_task = asyncio.create_task(
                RingGroup.ring(client, group, RingMode.SEQUENTIAL, timeout=2.0)
            )

            created_channels = await wait_for_channels(freeswitch, 1)
            first_channel_uuid = created_channels[0]

            await send_state_and_answer_events(freeswitch, client, first_channel_uuid)

            answered = await ring_task

            assert answered is not None
            assert answered.uuid == first_channel_uuid

            assert len(freeswitch.calls) == 1


@pytest.mark.asyncio
async def test_ring_group_sequential_second_answers(freeswitch):
    """Test sequential ring mode where second callee answers."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002"]

            ring_task = asyncio.create_task(
                RingGroup.ring(client, group, RingMode.SEQUENTIAL, timeout=0.5)
            )

            created_channels = await wait_for_channels(freeswitch, 1)
            first_channel_uuid = created_channels[0]

            created_channels = await wait_for_channels(freeswitch, 2, timeout=1.0)
            second_channel_uuid = [
                uuid for uuid in created_channels if uuid != first_channel_uuid
            ][0]

            await send_state_and_answer_events(freeswitch, client, second_channel_uuid)

            answered = await ring_task

            assert answered is not None, "Expected second channel to answer"
            assert answered.uuid == second_channel_uuid

            hangups = [uuid for uuid, _ in freeswitch.hangups]
            assert first_channel_uuid in hangups


@pytest.mark.asyncio
async def test_ring_group_sequential_no_answer(freeswitch):
    """Test sequential ring mode when no one answers."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002"]

            answered = await RingGroup.ring(
                client, group, RingMode.SEQUENTIAL, timeout=0.2
            )

            assert answered is None

            created_channels = list(freeswitch.calls.keys())
            assert len(created_channels) >= 1
            hangups = [uuid for uuid, _ in freeswitch.hangups]
            assert all(uuid in hangups for uuid in created_channels)


@pytest.mark.asyncio
async def test_ring_group_with_variables(freeswitch):
    """Test ring group with custom variables."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001"]
            variables = {"custom_var": "test_value"}

            ring_task = asyncio.create_task(
                RingGroup.ring(
                    client, group, RingMode.PARALLEL, timeout=2.0, variables=variables
                )
            )

            created_channels = await wait_for_channels(freeswitch, 1)
            channel_uuid = created_channels[0]

            assert any(
                "custom_var=test_value" in cmd for cmd in freeswitch.received_commands
            )

            await send_state_and_answer_events(freeswitch, client, channel_uuid)

            answered = await ring_task

            assert answered is not None
            assert answered.uuid == channel_uuid


@pytest.mark.asyncio
async def test_ring_group_with_load_balancer(freeswitch):
    """Test ring group with load balancer."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001", "user/1002", "user/1003"]
            lb = InMemoryLoadBalancer()

            ring_task = asyncio.create_task(
                RingGroup.ring(
                    client, group, RingMode.BALANCING, timeout=2.0, balancer=lb
                )
            )

            created_channels = await wait_for_channels(freeswitch, 1)

            assert len(created_channels) == 1
            first_dest = freeswitch.calls[created_channels[0]]
            assert await lb.get_count(first_dest) == 1

            first_channel_uuid = created_channels[0]
            await send_state_and_answer_events(freeswitch, client, first_channel_uuid)

            answered = await ring_task

            assert answered is not None
            assert answered.uuid == first_channel_uuid

            assert await lb.get_count(first_dest) == 0


@pytest.mark.asyncio
async def test_ring_group_balancing_shared_destination(freeswitch):
    """Test that load balancer works globally across different groups."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            lb = InMemoryLoadBalancer()

            group1 = ["user/1001", "user/1002"]
            group2 = ["user/1002", "user/1003"]

            ring_task1 = asyncio.create_task(
                RingGroup.ring(
                    client, group1, RingMode.BALANCING, timeout=2.0, balancer=lb
                )
            )

            created_channels1 = await wait_for_channels(freeswitch, 1)

            dest1 = freeswitch.calls[created_channels1[0]]
            assert await lb.get_count(dest1) == 1

            ring_task2 = asyncio.create_task(
                RingGroup.ring(
                    client, group2, RingMode.BALANCING, timeout=2.0, balancer=lb
                )
            )

            created_channels2 = await wait_for_channels(freeswitch, 2)

            dest2 = freeswitch.calls[created_channels2[1]]
            assert await lb.get_count(dest2) == 1

            if dest1 == "user/1002":
                assert await lb.get_count("user/1002") == 2
            else:
                assert await lb.get_count("user/1002") == 1

            first_channel_uuid = created_channels1[0]
            await send_state_and_answer_events(freeswitch, client, first_channel_uuid)

            answered1 = await ring_task1

            assert answered1 is not None
            assert await lb.get_count(dest1) == 0

            second_channel_uuid = created_channels2[1]
            await send_state_and_answer_events(freeswitch, client, second_channel_uuid)

            answered2 = await ring_task2

            assert answered2 is not None
            assert await lb.get_count(dest2) == 0

            for dest in group1 + group2:
                if dest != dest1 and dest != dest2:
                    assert await lb.get_count(dest) == 0


@pytest.mark.asyncio
async def test_ring_group_timeout_configuration(freeswitch):
    """Test that timeout parameter works correctly."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            group = ["user/1001"]

            start_time = asyncio.get_event_loop().time()
            answered = await RingGroup.ring(
                client, group, RingMode.PARALLEL, timeout=0.2
            )
            elapsed = asyncio.get_event_loop().time() - start_time

            assert answered is None
            assert 0.15 <= elapsed <= 0.5
