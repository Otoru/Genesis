"""Tests for the Session class in genesis.channels."""

import pytest
from asyncio import StreamReader, StreamWriter
from unittest.mock import AsyncMock, MagicMock, patch

from genesis.channels import Channel, Session, CommandResult, BackgroundJobResult
from genesis.enums import ChannelState
from genesis.exceptions import SessionGoneAway
from genesis.parser import ESLEvent


def create_mock_reader_writer():
    """Create mock StreamReader and StreamWriter for Session tests."""
    reader = MagicMock(spec=StreamReader)
    writer = MagicMock(spec=StreamWriter)
    return reader, writer


# ============================================================================
# Session Initialization Tests
# ============================================================================


class TestSessionInit:
    """Tests for Session initialization."""

    def test_session_init(self):
        """Test basic Session initialization."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        assert session.reader is reader
        assert session.writer is writer
        assert session.channels == {}
        assert session.channel_a is None
        assert session.myevents is False
        assert session.linger is True
        assert session.bgapi is not None

    def test_session_init_with_myevents(self):
        """Test Session initialization with myevents=True."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer, myevents=True)

        assert session.myevents is True

    def test_session_has_bgapi(self):
        """Test that Session has BackgroundAPI instance."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        assert hasattr(session, "bgapi")
        assert session.bgapi is not None


# ============================================================================
# Session Event Dispatch Tests
# ============================================================================


class TestSessionEventDispatch:
    """Tests for Session._dispatch_event_to_channels()."""

    @pytest.mark.asyncio
    async def test_dispatch_creates_channel_on_channel_create(self):
        """Test that CHANNEL_CREATE event creates a Channel instance."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        # Mock send to avoid actual network calls
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        event = ESLEvent(
            {
                "Event-Name": "CHANNEL_CREATE",
                "Unique-ID": "new-channel-uuid",
                "Channel-State": "CS_NEW",
            }
        )

        await session._dispatch_event_to_channels(event)

        assert "new-channel-uuid" in session.channels
        assert isinstance(session.channels["new-channel-uuid"], Channel)

    @pytest.mark.asyncio
    async def test_dispatch_sets_channel_a_for_first_channel(self):
        """Test that the first channel created becomes channel_a."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        event = ESLEvent(
            {
                "Event-Name": "CHANNEL_CREATE",
                "Unique-ID": "first-channel-uuid",
                "Channel-State": "CS_NEW",
            }
        )

        await session._dispatch_event_to_channels(event)

        assert session.channel_a is not None
        assert session.channel_a.uuid == "first-channel-uuid"

    @pytest.mark.asyncio
    async def test_dispatch_does_not_overwrite_channel_a(self):
        """Test that subsequent channels don't overwrite channel_a."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        # First channel
        first_event = ESLEvent(
            {
                "Event-Name": "CHANNEL_CREATE",
                "Unique-ID": "first-uuid",
                "Channel-State": "CS_NEW",
            }
        )
        await session._dispatch_event_to_channels(first_event)

        # Second channel
        second_event = ESLEvent(
            {
                "Event-Name": "CHANNEL_CREATE",
                "Unique-ID": "second-uuid",
                "Channel-State": "CS_NEW",
            }
        )
        await session._dispatch_event_to_channels(second_event)

        assert session.channel_a.uuid == "first-uuid"
        assert "second-uuid" in session.channels

    @pytest.mark.asyncio
    async def test_dispatch_removes_channel_on_destroy(self):
        """Test that CHANNEL_DESTROY event removes the channel."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        # Create channel first
        channel = Channel(uuid="test-uuid", session=session)
        session.channels["test-uuid"] = channel

        # Dispatch destroy event
        destroy_event = ESLEvent(
            {
                "Event-Name": "CHANNEL_DESTROY",
                "Unique-ID": "test-uuid",
            }
        )
        await session._dispatch_event_to_channels(destroy_event)

        assert "test-uuid" not in session.channels

    @pytest.mark.asyncio
    async def test_dispatch_clears_channel_a_on_destroy(self):
        """Test that destroying channel_a clears the reference."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        channel = Channel(uuid="a-leg-uuid", session=session)
        session.channels["a-leg-uuid"] = channel
        session.channel_a = channel

        destroy_event = ESLEvent(
            {
                "Event-Name": "CHANNEL_DESTROY",
                "Unique-ID": "a-leg-uuid",
            }
        )
        await session._dispatch_event_to_channels(destroy_event)

        assert session.channel_a is None

    @pytest.mark.asyncio
    async def test_dispatch_ignores_events_without_uuid(self):
        """Test that events without channel UUID are ignored."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        event = ESLEvent({"Event-Name": "HEARTBEAT"})

        # Should not raise, should just return
        await session._dispatch_event_to_channels(event)

        assert len(session.channels) == 0


# ============================================================================
# Session Sendmsg Tests
# ============================================================================


class TestSessionSendmsg:
    """Tests for Session.sendmsg()."""

    @pytest.mark.asyncio
    async def test_sendmsg_execute_command(self):
        """Test sendmsg with execute command."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        # Need to mock the _awaitable_complete_command to prevent waiting forever
        complete_event = MagicMock()
        complete_event.wait = AsyncMock()
        session._awaitable_complete_command = AsyncMock(return_value=complete_event)

        result = await session.sendmsg("execute", "playback", "/path/to/file.wav")

        assert result is not None
        assert isinstance(result, CommandResult)
        session.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_sendmsg_hangup_command(self):
        """Test sendmsg with hangup command."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "+OK hangup succeeded"})
        )

        result = await session.sendmsg("hangup", "", "NORMAL_CLEARING")

        assert result is not None
        assert result.is_completed

    @pytest.mark.asyncio
    async def test_sendmsg_with_uuid(self):
        """Test sendmsg with specific channel UUID."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))

        complete_event = MagicMock()
        complete_event.wait = AsyncMock()
        session._awaitable_complete_command = AsyncMock(return_value=complete_event)

        result = await session.sendmsg(
            "execute", "answer", uuid="specific-channel-uuid"
        )

        # Check that the command was sent with the UUID
        call_args = session.send.call_args[0][0]
        assert "sendmsg specific-channel-uuid" in call_args


# ============================================================================
# Session Convenience Method Tests
# ============================================================================


class TestSessionConvenienceMethods:
    """Tests for Session convenience methods."""

    @pytest.mark.asyncio
    async def test_answer(self):
        """Test Session.answer() method."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.answer()

        session.sendmsg.assert_called_once_with("execute", "answer")

    @pytest.mark.asyncio
    async def test_park(self):
        """Test Session.park() method."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.park()

        session.sendmsg.assert_called_once_with("execute", "park")

    @pytest.mark.asyncio
    async def test_hangup(self):
        """Test Session.hangup() method."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.hangup()

        session.sendmsg.assert_called_once_with("execute", "hangup", "NORMAL_CLEARING")

    @pytest.mark.asyncio
    async def test_hangup_with_cause(self):
        """Test Session.hangup() with custom cause."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.hangup("USER_BUSY")

        session.sendmsg.assert_called_once_with("execute", "hangup", "USER_BUSY")

    @pytest.mark.asyncio
    async def test_playback(self):
        """Test Session.playback() method."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.playback("/path/to/audio.wav")

        session.sendmsg.assert_called_once_with(
            "execute", "playback", "/path/to/audio.wav"
        )

    @pytest.mark.asyncio
    async def test_log(self):
        """Test Session.log() method."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.sendmsg = AsyncMock(return_value=MagicMock(spec=CommandResult))

        await session.log("INFO", "Test message")

        session.sendmsg.assert_called_once_with("execute", "log", "INFO Test message")


# ============================================================================
# Session Bridge Tests
# ============================================================================


class TestSessionBridge:
    """Tests for Session.bridge() method."""

    @pytest.mark.asyncio
    async def test_bridge_delegates_to_channel(self):
        """Test that Session.bridge() delegates to Channel.bridge()."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        channel_a = MagicMock(spec=Channel)
        channel_a.uuid = "a-leg-uuid"
        channel_a.is_gone = False

        mock_result = MagicMock(spec=CommandResult)
        mock_b_leg = MagicMock(spec=Channel)
        channel_a.bridge = AsyncMock(return_value=(mock_result, mock_b_leg))

        result = await session.bridge(channel_a, "user/1000", {"key": "value"})

        channel_a.bridge.assert_called_once_with("user/1000", {"key": "value"})
        assert result == (mock_result, mock_b_leg)

    @pytest.mark.asyncio
    async def test_bridge_raises_when_channel_gone(self):
        """Test that bridge raises SessionGoneAway when channel is gone."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        channel_a = MagicMock(spec=Channel)
        channel_a.uuid = "a-leg-uuid"
        channel_a.is_gone = True

        with pytest.raises(SessionGoneAway):
            await session.bridge(channel_a, "user/1000")


# ============================================================================
# Session Unbridge Tests
# ============================================================================


class TestSessionUnbridge:
    """Tests for Session.unbridge() method."""

    @pytest.mark.asyncio
    async def test_unbridge_by_uuid(self):
        """Test unbridge by channel UUID string."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        channel = MagicMock(spec=Channel)
        channel.uuid = "test-uuid"
        channel.unbridge = AsyncMock(return_value=MagicMock(spec=BackgroundJobResult))
        session.channels["test-uuid"] = channel

        result = await session.unbridge("test-uuid")

        channel.unbridge.assert_called_once_with(destination=None, park=True)

    @pytest.mark.asyncio
    async def test_unbridge_by_channel_object(self):
        """Test unbridge by Channel object."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        channel = MagicMock(spec=Channel)
        channel.uuid = "test-uuid"
        channel.unbridge = AsyncMock(return_value=MagicMock(spec=BackgroundJobResult))

        result = await session.unbridge(channel, destination="/transfer/dest")

        channel.unbridge.assert_called_once_with(
            destination="/transfer/dest", park=True
        )

    @pytest.mark.asyncio
    async def test_unbridge_raises_for_unknown_uuid(self):
        """Test that unbridge raises SessionGoneAway for unknown UUID."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        with pytest.raises(SessionGoneAway):
            await session.unbridge("nonexistent-uuid")

    @pytest.mark.asyncio
    async def test_unbridge_raises_for_invalid_type(self):
        """Test that unbridge raises TypeError for invalid channel type."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        with pytest.raises(TypeError):
            await session.unbridge(12345)  # type: ignore


# ============================================================================
# Session Originate Tests
# ============================================================================


class TestSessionOriginate:
    """Tests for Session.originate() method."""

    @pytest.mark.asyncio
    async def test_originate_delegates_to_channel_class(self):
        """Test that Session.originate() delegates to Channel.originate()."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        mock_channel = MagicMock(spec=Channel)

        with patch.object(
            Channel, "originate", new_callable=AsyncMock
        ) as mock_originate:
            mock_originate.return_value = mock_channel

            result = await session.originate(
                destination="sofia/gateway/mygw/1234",
                uuid="custom-uuid",
                variables={"key": "value"},
                timeout=30,
                application_after="bridge",
            )

            mock_originate.assert_called_once_with(
                session=session,
                destination="sofia/gateway/mygw/1234",
                uuid="custom-uuid",
                variables={"key": "value"},
                timeout=30,
                application_after="bridge",
            )
            assert result is mock_channel


# ============================================================================
# Session BGApi Execute Tests
# ============================================================================


class TestSessionBgapiExecute:
    """Tests for Session.bgapi_execute() method."""

    @pytest.mark.asyncio
    async def test_bgapi_execute_delegates_to_bgapi(self):
        """Test that bgapi_execute delegates to BackgroundAPI.execute()."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        mock_result = MagicMock(spec=BackgroundJobResult)
        session.bgapi.execute = AsyncMock(return_value=mock_result)

        result = await session.bgapi_execute("originate user/1000 &park()")

        session.bgapi.execute.assert_called_once_with(
            "originate user/1000 &park()", None
        )
        assert result is mock_result

    @pytest.mark.asyncio
    async def test_bgapi_execute_with_custom_job_uuid(self):
        """Test bgapi_execute with custom job UUID."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)

        mock_result = MagicMock(spec=BackgroundJobResult)
        session.bgapi.execute = AsyncMock(return_value=mock_result)

        await session.bgapi_execute("some_command", job_uuid="my-job-uuid")

        session.bgapi.execute.assert_called_once_with("some_command", "my-job-uuid")


# ============================================================================
# Session Context Manager Tests
# ============================================================================


class TestSessionContextManager:
    """Tests for Session async context manager."""

    @pytest.mark.asyncio
    async def test_aenter_calls_start(self):
        """Test that __aenter__ calls start()."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.start = AsyncMock()

        async with session as s:
            session.start.assert_called_once()
            assert s is session

    @pytest.mark.asyncio
    async def test_aexit_calls_stop(self):
        """Test that __aexit__ calls stop()."""
        reader, writer = create_mock_reader_writer()
        session = Session(reader, writer)
        session.start = AsyncMock()
        session.stop = AsyncMock()

        async with session:
            pass

        session.stop.assert_called_once()
