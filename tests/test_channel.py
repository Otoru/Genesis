"""Tests for the Channel class in genesis.channels."""

import pytest
from asyncio import Event
from unittest.mock import AsyncMock, MagicMock, patch

from genesis.channels import Channel, CommandResult
from genesis.enums import CallState, ChannelState
from genesis.exceptions import SessionGoneAway
from genesis.parser import ESLEvent


class MockSession:
    """Mock Session for testing Channel."""

    def __init__(self):
        self.channels = {}
        self.sent_commands = []
        self.handlers = {}
        self.bgapi = MagicMock()
        self.bgapi.execute = AsyncMock()

    def on(self, event_name, handler):
        """Register an event handler."""
        self.handlers.setdefault(event_name, []).append(handler)

    def remove(self, event_name, handler):
        """Remove an event handler."""
        if event_name in self.handlers and handler in self.handlers[event_name]:
            self.handlers[event_name].remove(handler)

    async def send(self, cmd):
        """Mock send command."""
        self.sent_commands.append(cmd)
        return ESLEvent({"Reply-Text": "+OK"})

    async def sendmsg(
        self,
        command,
        application,
        data=None,
        lock=False,
        uuid=None,
        app_event_uuid=None,
        headers=None,
    ):
        """Mock sendmsg command."""
        self.sent_commands.append(
            {
                "command": command,
                "application": application,
                "data": data,
                "uuid": uuid,
                "app_event_uuid": app_event_uuid,
            }
        )
        result = CommandResult(
            initial_event=ESLEvent({"Reply-Text": "+OK"}),
            channel_uuid=uuid,
            command=command,
            application=application,
            data=data,
        )
        result.set_complete(ESLEvent({"Reply-Text": "+OK"}))
        return result

    async def bgapi_execute(self, cmd, job_uuid=None):
        """Mock bgapi execute."""
        return await self.bgapi.execute(cmd, job_uuid)


# ============================================================================
# Channel Initialization Tests
# ============================================================================


class TestChannelInit:
    """Tests for Channel initialization."""

    def test_channel_init_basic(self):
        """Test basic Channel initialization."""
        session = MockSession()
        channel = Channel(uuid="test-uuid-123", session=session)

        assert channel.uuid == "test-uuid-123"
        assert channel.session is session
        assert channel.state == ChannelState.NEW
        assert channel.call_state == CallState.DOWN
        assert channel.variables == {}
        assert channel.is_gone is False
        assert channel.handlers == {}

    def test_channel_init_with_initial_state(self):
        """Test Channel initialization with custom initial state."""
        session = MockSession()
        channel = Channel(
            uuid="test-uuid-123",
            session=session,
            initial_state=ChannelState.EXECUTE,
        )

        assert channel.state == ChannelState.EXECUTE

    def test_channel_repr(self):
        """Test Channel string representation."""
        session = MockSession()
        channel = Channel(uuid="abc-123", session=session)

        repr_str = repr(channel)
        assert "abc-123" in repr_str
        assert "NEW" in repr_str
        assert "DOWN" in repr_str


# ============================================================================
# Channel Event Handler Tests
# ============================================================================


class TestChannelEventHandlers:
    """Tests for Channel event handling."""

    def test_on_registers_handler(self):
        """Test that on() registers event handlers."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        def my_handler(ch, event):
            pass

        channel.on("DTMF", my_handler)

        assert "DTMF" in channel.handlers
        assert my_handler in channel.handlers["DTMF"]

    def test_on_normalizes_event_name(self):
        """Test that event names are normalized to uppercase."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        def my_handler(ch, event):
            pass

        channel.on("dtmf", my_handler)

        assert "DTMF" in channel.handlers

    def test_on_raises_for_non_callable(self):
        """Test that on() raises TypeError for non-callable handlers."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        with pytest.raises(TypeError):
            channel.on("DTMF", "not a callable")

    def test_remove_removes_handler(self):
        """Test that remove() removes event handlers."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        def my_handler(ch, event):
            pass

        channel.on("DTMF", my_handler)
        channel.remove("DTMF", my_handler)

        assert "DTMF" not in channel.handlers

    def test_remove_nonexistent_handler_no_error(self):
        """Test that removing a non-existent handler doesn't raise."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        def my_handler(ch, event):
            pass

        # Should not raise
        channel.remove("DTMF", my_handler)


# ============================================================================
# Channel State Update Tests
# ============================================================================


class TestChannelStateUpdate:
    """Tests for Channel.update_state()."""

    def test_update_state_from_event(self):
        """Test state update from ESLEvent Channel-State-Number."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent({"Channel-State-Number": "4"})
        channel.update_state(event)

        # State 4 = CS_EXECUTE
        assert channel.state == ChannelState.EXECUTE

    def test_update_call_state_from_event(self):
        """Test call state update from ESLEvent Channel-Call-State."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent({"Channel-Call-State": "ACTIVE"})
        channel.update_state(event)

        assert channel.call_state == CallState.ACTIVE

    def test_update_call_state_early_media_mapped(self):
        """Test that EARLY_MEDIA is mapped to EARLY."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent({"Channel-Call-State": "EARLY_MEDIA"})
        channel.update_state(event)

        assert channel.call_state == CallState.EARLY

    def test_update_state_marks_gone_on_hangup(self):
        """Test that channel is marked gone on HANGUP call state."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent({"Channel-Call-State": "HANGUP"})
        channel.update_state(event)

        assert channel.is_gone is True
        assert channel.call_state == CallState.HANGUP

    def test_update_state_marks_gone_on_destroy(self):
        """Test that channel is marked gone on DESTROY core state."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        # CS_DESTROY = 12
        event = ESLEvent({"Channel-State-Number": "12"})
        channel.update_state(event)

        assert channel.is_gone is True
        assert channel.state == ChannelState.DESTROY

    def test_update_state_captures_variables(self):
        """Test that channel variables are captured from events."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent(
            {
                "variable_my_custom_var": "my_value",
                "Caller-Caller-ID-Number": "1234567890",
            }
        )
        channel.update_state(event)

        assert channel.variables.get("my_custom_var") == "my_value"
        assert channel.variables.get("Caller-Caller-ID-Number") == "1234567890"

    def test_update_state_ignores_invalid_state_number(self):
        """Test that invalid state numbers are handled gracefully."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent({"Channel-State-Number": "999"})
        channel.update_state(event)

        # State should remain NEW (default)
        assert channel.state == ChannelState.NEW


# ============================================================================
# Channel Command Tests
# ============================================================================


class TestChannelCommands:
    """Tests for Channel command methods."""

    @pytest.mark.asyncio
    async def test_answer(self):
        """Test Channel.answer() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.answer()

        assert result is not None
        assert any(cmd.get("application") == "answer" for cmd in session.sent_commands)

    @pytest.mark.asyncio
    async def test_park(self):
        """Test Channel.park() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.park()

        assert result is not None
        assert any(cmd.get("application") == "park" for cmd in session.sent_commands)

    @pytest.mark.asyncio
    async def test_hangup(self):
        """Test Channel.hangup() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.hangup()

        assert result is not None
        assert any(cmd.get("command") == "hangup" for cmd in session.sent_commands)

    @pytest.mark.asyncio
    async def test_hangup_with_cause(self):
        """Test Channel.hangup() with custom cause."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.hangup(cause="USER_BUSY")

        assert result is not None
        assert any(cmd.get("data") == "USER_BUSY" for cmd in session.sent_commands)

    @pytest.mark.asyncio
    async def test_hangup_already_gone(self):
        """Test Channel.hangup() when channel is already gone."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        channel.is_gone = True

        result = await channel.hangup()

        # Should return result without sending command
        assert result is not None
        assert result.is_completed
        assert len(session.sent_commands) == 0

    @pytest.mark.asyncio
    async def test_playback(self):
        """Test Channel.playback() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.playback("/path/to/audio.wav")

        assert result is not None
        assert any(
            cmd.get("application") == "playback" for cmd in session.sent_commands
        )

    @pytest.mark.asyncio
    async def test_silence(self):
        """Test Channel.silence() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.silence(1000)

        assert result is not None
        # Should call playback with silence_stream://1000
        matching_cmds = [
            cmd
            for cmd in session.sent_commands
            if cmd.get("data") and "silence_stream://1000" in cmd.get("data")
        ]
        assert len(matching_cmds) > 0

    @pytest.mark.asyncio
    async def test_set_variable(self):
        """Test Channel.set_variable() method."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.set_variable("my_var", "my_value")

        assert result is not None
        assert any(
            cmd.get("data") == "my_var=my_value" for cmd in session.sent_commands
        )

    @pytest.mark.asyncio
    async def test_get_variable_from_cache(self):
        """Test Channel.get_variable() from local cache."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        channel.variables["my_var"] = "cached_value"

        value = await channel.get_variable("my_var")

        assert value == "cached_value"

    @pytest.mark.asyncio
    async def test_get_variable_not_found(self):
        """Test Channel.get_variable() when variable not in cache."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        value = await channel.get_variable("nonexistent")

        assert value is None

    @pytest.mark.asyncio
    async def test_execute_generic(self):
        """Test Channel.execute() with a generic application."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        result = await channel.execute("some_app", "some_args")

        assert result is not None
        assert any(
            cmd.get("application") == "some_app" for cmd in session.sent_commands
        )


# ============================================================================
# Channel Gone Check Tests
# ============================================================================


class TestChannelGoneCheck:
    """Tests for checking if channel is gone."""

    @pytest.mark.asyncio
    async def test_command_raises_when_gone(self):
        """Test that commands raise SessionGoneAway when channel is gone."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        channel.is_gone = True

        with pytest.raises(SessionGoneAway):
            await channel.execute("playback", "test.wav")

    @pytest.mark.asyncio
    async def test_get_variable_raises_when_gone(self):
        """Test that get_variable raises SessionGoneAway when channel is gone."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        channel.is_gone = True

        with pytest.raises(SessionGoneAway):
            await channel.get_variable("some_var")


# ============================================================================
# Channel Bridge Tests
# ============================================================================


class TestChannelBridge:
    """Tests for Channel.bridge() method."""

    @pytest.mark.asyncio
    async def test_bridge_to_string_target(self):
        """Test bridging to a string target (creates B-leg channel)."""
        session = MockSession()
        channel = Channel(uuid="a-leg-uuid", session=session)
        session.channels["a-leg-uuid"] = channel

        result = await channel.bridge("user/1000")

        # Should return tuple of (CommandResult, Channel)
        assert isinstance(result, tuple)
        command_result, b_leg_channel = result
        assert isinstance(command_result, CommandResult)
        assert isinstance(b_leg_channel, Channel)
        assert b_leg_channel.uuid in session.channels

    @pytest.mark.asyncio
    async def test_bridge_to_channel_object(self):
        """Test bridging to an existing Channel object (uuid_bridge)."""
        session = MockSession()
        channel_a = Channel(uuid="a-leg-uuid", session=session)
        channel_b = Channel(uuid="b-leg-uuid", session=session)
        session.channels["a-leg-uuid"] = channel_a
        session.channels["b-leg-uuid"] = channel_b

        # Mock bgapi to return a result
        mock_result = MagicMock()
        session.bgapi.execute.return_value = mock_result

        result = await channel_a.bridge(channel_b)

        # Should call bgapi execute with uuid_bridge
        session.bgapi.execute.assert_called_once()
        call_args = session.bgapi.execute.call_args[0][0]
        assert "uuid_bridge" in call_args
        assert "a-leg-uuid" in call_args
        assert "b-leg-uuid" in call_args

    @pytest.mark.asyncio
    async def test_bridge_raises_when_gone(self):
        """Test that bridge raises SessionGoneAway when A-leg is gone."""
        session = MockSession()
        channel = Channel(uuid="a-leg-uuid", session=session)
        channel.is_gone = True

        with pytest.raises(SessionGoneAway):
            await channel.bridge("user/1000")


# ============================================================================
# Channel Handle Event Tests
# ============================================================================


class TestChannelHandleEvent:
    """Tests for Channel._handle_event()."""

    @pytest.mark.asyncio
    async def test_handle_event_calls_handler(self):
        """Test that _handle_event calls registered handlers."""
        import asyncio

        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        called = []

        async def my_handler(ch, event):
            called.append(event)

        channel.on("DTMF", my_handler)

        event = ESLEvent({"Event-Name": "DTMF", "DTMF-Digit": "5"})
        await channel._handle_event(event)
        # Give event loop a chance to run scheduled tasks from create_task
        await asyncio.sleep(0)

        assert len(called) == 1
        assert called[0]["DTMF-Digit"] == "5"

    @pytest.mark.asyncio
    async def test_handle_event_wildcard_handler(self):
        """Test that wildcard handler is called for all events."""
        import asyncio

        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)
        called = []

        async def wildcard_handler(ch, event):
            called.append(event.get("Event-Name"))

        channel.on("*", wildcard_handler)

        await channel._handle_event(ESLEvent({"Event-Name": "DTMF"}))
        await asyncio.sleep(0)
        await channel._handle_event(ESLEvent({"Event-Name": "CHANNEL_ANSWER"}))
        await asyncio.sleep(0)

        assert "DTMF" in called
        assert "CHANNEL_ANSWER" in called

    @pytest.mark.asyncio
    async def test_handle_event_updates_state(self):
        """Test that _handle_event updates channel state."""
        session = MockSession()
        channel = Channel(uuid="test-uuid", session=session)

        event = ESLEvent(
            {
                "Event-Name": "CHANNEL_ANSWER",
                "Channel-State-Number": "4",
                "Channel-Call-State": "ACTIVE",
            }
        )
        await channel._handle_event(event)

        assert channel.state == ChannelState.EXECUTE
        assert channel.call_state == CallState.ACTIVE

        
# Conflicting changes :(


import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from genesis import Channel, Session, Inbound, Outbound
from genesis.types import ChannelState
from genesis.exceptions import TimeoutError
from tests.payloads import channel_answer, channel_state
from tests.test_group import wait_for_state_event_processed


@pytest.mark.asyncio
async def test_channel_start(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            assert channel.uuid is not None

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
            await dialplan.start(*outbound_address)
            await asyncio.wait_for(bridge_complete.wait(), timeout=2.0)

            await dialplan.stop()
            await app.stop()

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

            assert channel.uuid is not None

            originate_cmd = None
            for cmd in freeswitch.received_commands:
                if "originate" in cmd:
                    originate_cmd = cmd
                    break

            assert originate_cmd is not None
            assert channel.uuid in originate_cmd
            assert "origination_caller_id_number=11999999999" in originate_cmd
            assert "origination_caller_id_name=Test" in originate_cmd
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

            assert channel.uuid is not None
            assert channel.uuid != "should-not-override"

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

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)
            await wait_for_state_event_processed(
                client, channel.uuid, "CS_ROUTING", timeout=1.0
            )

            result = await channel.wait(ChannelState.ROUTING, timeout=1.0)
            assert result is None
            assert channel.state == ChannelState.ROUTING


@pytest.mark.asyncio
async def test_channel_wait_already_hangup(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_HANGUP",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)
            await wait_for_state_event_processed(
                client, channel.uuid, "CS_HANGUP", timeout=1.0
            )

            result = await channel.wait(ChannelState.EXECUTE, timeout=1.0)
            assert result is None


@pytest.mark.asyncio
async def test_channel_wait_timeout(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            with pytest.raises(TimeoutError, match="Channel did not reach EXECUTE"):
                await channel.wait(ChannelState.EXECUTE, timeout=0.1)


@pytest.mark.asyncio
async def test_channel_wait_state_change(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            wait_task = asyncio.create_task(
                channel.wait(ChannelState.ROUTING, timeout=1.0)
            )

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)

            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.ROUTING


@pytest.mark.asyncio
async def test_channel_wait_execute_with_answer(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            wait_task = asyncio.create_task(
                channel.wait(ChannelState.EXECUTE, timeout=1.0)
            )

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_EXECUTE",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)
            await wait_for_state_event_processed(
                client, channel.uuid, "CS_EXECUTE", timeout=1.0
            )

            answer_event = channel_answer.format(unique_id=channel.uuid)
            await freeswitch.broadcast(answer_event)

            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.EXECUTE


@pytest.mark.asyncio
async def test_channel_wait_execute_answer_first(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")

            wait_task = asyncio.create_task(
                channel.wait(ChannelState.EXECUTE, timeout=1.0)
            )

            answer_event = channel_answer.format(unique_id=channel.uuid)
            await freeswitch.broadcast(answer_event)

            event_body = channel_state.format(
                unique_id=channel.uuid,
                state="CS_EXECUTE",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(event_body)

            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.EXECUTE


@pytest.mark.asyncio
async def test_channel_wait_ignores_other_channel_events(freeswitch):
    async with freeswitch:
        async with Inbound(*freeswitch.address) as client:
            channel = await Channel.create(client, "user/1000")
            other_channel = await Channel.create(client, "user/2000")

            wait_task = asyncio.create_task(
                channel.wait(ChannelState.ROUTING, timeout=1.0)
            )

            other_event = channel_state.format(
                unique_id=other_channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(other_event)

            correct_event = channel_state.format(
                unique_id=channel.uuid,
                state="CS_ROUTING",
                variable_test_key="test_value",
            )
            await freeswitch.broadcast(correct_event)

            result = await wait_task
            assert result is not None
            assert channel.state == ChannelState.ROUTING
