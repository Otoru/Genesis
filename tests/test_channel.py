import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from genesis import Channel, Session, Inbound, Outbound
from genesis.types import ChannelState
from genesis.exceptions import TimeoutError


@pytest.mark.asyncio
async def test_channel_start(freeswitch):
    async with freeswitch:
        # Client connects to the mock server logic provided by fixture
        async with Inbound(*freeswitch.address) as client:
            # Setup Channel with Inbound Client
            channel = await Channel.create(client, "user/1000")

            # Verify UUID was set
            assert channel.uuid is not None

            # Verify originate command
            expected_originate = f"api originate {{origination_uuid={channel.uuid},return_ring_ready=true}}user/1000 &park()"
            assert expected_originate in freeswitch.received_commands
            assert freeswitch.calls[channel.uuid] == "user/1000"


@pytest.mark.asyncio
async def test_channel_hangup(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            await channel.hangup()

            assert (channel.uuid, "NORMAL_CLEARING") in freeswitch.hangups


@pytest.mark.asyncio
async def test_channel_hangup_custon_cause(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            await channel.hangup("USER_BUSY")

            assert (channel.uuid, "USER_BUSY") in freeswitch.hangups


@pytest.mark.asyncio
async def test_channel_bridge_with_another_channel(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel_a = await Channel.create(client, "user/1000")
            channel_b = await Channel.create(client, "user/2000")

            await channel_a.bridge(channel_b)

            assert (channel_a.uuid, channel_b.uuid) in freeswitch.bridges


@pytest.mark.asyncio
async def test_channel_bridge_with_session(freeswitch, host, port, dialplan):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Setup Outbound server to provide a real Session
            bridge_complete = asyncio.Event()
            captured_uuid: asyncio.Future[str] = asyncio.Future()

            async def handler(session: Session) -> None:
                if session.uuid:
                    captured_uuid.set_result(session.uuid)
                await channel.bridge(session)
                bridge_complete.set()

            outbound_address = (host(), port())
            app = Outbound(handler, *outbound_address)
            await app.start(block=False)

            # Connect Dialplan to Outbound server to trigger the handler
            await dialplan.start(*outbound_address)

            # Wait for bridge to complete
            await asyncio.wait_for(bridge_complete.wait(), timeout=2.0)

            await dialplan.stop()
            await app.stop()

            # Verify bridge command was sent with correct UUIDs
            assert (channel.uuid, captured_uuid.result()) in freeswitch.bridges


@pytest.mark.asyncio
async def test_channel_create_with_variables(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            variables = {
                "origination_caller_id_number": "11999999999",
                "origination_caller_id_name": "Test",
            }
            channel = await Channel.create(client, "user/1000", variables)

            # Verify UUID was set
            assert channel.uuid is not None

            # Find the originate command
            originate_cmd = None
            for cmd in freeswitch.received_commands:
                if "originate" in cmd:
                    originate_cmd = cmd
                    break

            assert originate_cmd is not None
            # Verify originate command includes custom variables
            assert channel.uuid in originate_cmd
            assert "origination_caller_id_number=11999999999" in originate_cmd
            assert "origination_caller_id_name=Test" in originate_cmd
            # Verify default variables are still present
            assert "return_ring_ready=true" in originate_cmd


@pytest.mark.asyncio
async def test_channel_create_variables_cannot_override_defaults(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            variables = {
                "origination_uuid": "should-not-override",
                "return_ring_ready": "false",
            }
            channel = await Channel.create(client, "user/1000", variables)

            # Verify default variables were not overridden
            assert channel.uuid is not None
            assert channel.uuid != "should-not-override"

            # Find the originate command
            originate_cmd = None
            for cmd in freeswitch.received_commands:
                if "originate" in cmd:
                    originate_cmd = cmd
                    break

            assert originate_cmd is not None
            assert f"origination_uuid={channel.uuid}" in originate_cmd
            assert "return_ring_ready=true" in originate_cmd
            assert "return_ring_ready=false" not in originate_cmd


@pytest.mark.asyncio
async def test_channel_wait_already_in_state(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Set state to ROUTING
            from tests.payloads import channel_state

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)
            await asyncio.sleep(0.1)

            # Wait for ROUTING (already in state, should return immediately)
            result = await channel.wait(ChannelState.ROUTING, timeout=1.0)
            assert result is None
            assert channel.state == ChannelState.ROUTING


@pytest.mark.asyncio
async def test_channel_wait_already_hangup(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Set state to HANGUP
            from tests.payloads import channel_state

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_HANGUP",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)
            await asyncio.sleep(0.1)

            # Wait should return None immediately
            result = await channel.wait(ChannelState.EXECUTE, timeout=1.0)
            assert result is None


@pytest.mark.asyncio
async def test_channel_wait_timeout(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            # Wait for EXECUTE without sending events (should timeout)
            from genesis.exceptions import TimeoutError

            with pytest.raises(TimeoutError, match="Channel did not reach EXECUTE"):
                await channel.wait(ChannelState.EXECUTE, timeout=0.1)


@pytest.mark.asyncio
async def test_channel_wait_state_change(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            from tests.payloads import channel_state

            # Wait for ROUTING state
            wait_task = asyncio.create_task(
                channel.wait(ChannelState.ROUTING, timeout=1.0)
            )

            # Send ROUTING event after a short delay
            await asyncio.sleep(0.1)
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)

            # Wait should complete
            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.ROUTING


@pytest.mark.asyncio
async def test_channel_wait_execute_with_answer(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            from tests.payloads import channel_state

            # Wait for EXECUTE state
            wait_task = asyncio.create_task(
                channel.wait(ChannelState.EXECUTE, timeout=1.0)
            )

            # Send EXECUTE event first
            await asyncio.sleep(0.05)
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_EXECUTE",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)

            # Send CHANNEL_ANSWER event (required for EXECUTE)
            await asyncio.sleep(0.05)
            answer_event = f"""Event-Name: CHANNEL_ANSWER
Unique-ID: {channel.uuid}
"""
            await freeswitch.broadcast(answer_event)

            # Wait should complete after both events
            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.EXECUTE


@pytest.mark.asyncio
async def test_channel_wait_execute_answer_first(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            from tests.payloads import channel_state

            # Wait for EXECUTE state
            wait_task = asyncio.create_task(
                channel.wait(ChannelState.EXECUTE, timeout=1.0)
            )

            # Send CHANNEL_ANSWER event first
            await asyncio.sleep(0.05)
            answer_event = f"""Event-Name: CHANNEL_ANSWER
Unique-ID: {channel.uuid}
"""
            await freeswitch.broadcast(answer_event)

            # Send EXECUTE event after
            await asyncio.sleep(0.05)
            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_EXECUTE",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)

            # Wait should complete after both events
            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.EXECUTE


@pytest.mark.asyncio
async def test_channel_wait_ignores_other_channel_events(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")
            other_channel = await Channel.create(client, "user/2000")

            from tests.payloads import channel_state

            # Wait for ROUTING state
            wait_task = asyncio.create_task(
                channel.wait(ChannelState.ROUTING, timeout=1.0)
            )

            # Send event for other channel (should be ignored)
            await asyncio.sleep(0.05)
            other_event = channel_state.format(
                unique_id=other_channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(other_event)

            # Send event for correct channel
            await asyncio.sleep(0.05)
            correct_event = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(correct_event)

            # Wait should complete only after correct event
            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.ROUTING
