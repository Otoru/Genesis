import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from genesis.channel import Channel
from genesis.enums import ChannelState, CallState
from genesis.events import ESLEvent
from genesis.exceptions import SessionGoneAway, OriginateError
from genesis.results import CommandResult, BackgroundJobResult


class TestChannel:
    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.channels = {}
        session.send = AsyncMock()
        session.sendmsg = AsyncMock()
        return session

    @pytest.fixture
    def channel(self, mock_session):
        uuid = str(uuid4())
        return Channel(uuid=uuid, session=mock_session)

    def test_channel_initialization(self, channel):
        assert channel.uuid is not None
        assert channel.state == ChannelState.NEW
        assert channel.call_state == CallState.DOWN
        assert channel.variables == {}
        assert not channel.is_gone
        assert channel.handlers == {}

    def test_channel_repr(self, channel):
        repr_str = repr(channel)
        assert channel.uuid in repr_str
        assert "NEW" in repr_str
        assert "DOWN" in repr_str

    async def test_channel_execute(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.execute("playback", "/tmp/test.wav")
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="playback", 
            data="/tmp/test.wav",
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )
        assert result == mock_result

    async def test_channel_hangup(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.hangup("BUSY")
        
        channel.session.sendmsg.assert_called_once_with(
            command="hangup",
            application="",
            data="BUSY",
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )

    async def test_channel_hangup_when_already_gone(self, channel):
        channel.is_gone = True
        
        result = await channel.hangup()
        
        # Should not call sendmsg when channel is already gone
        channel.session.sendmsg.assert_not_called()
        assert result.is_completed

    def test_channel_check_if_gone_raises_exception(self, channel):
        channel.is_gone = True
        
        with pytest.raises(SessionGoneAway):
            channel._check_if_gone()

    def test_channel_event_handler_registration(self, channel):
        handler = AsyncMock()
        
        channel.on("DTMF", handler)
        
        assert "DTMF" in channel.handlers
        assert handler in channel.handlers["DTMF"]

    def test_channel_event_handler_removal(self, channel):
        handler = AsyncMock()
        channel.on("DTMF", handler)
        
        channel.remove("DTMF", handler)
        
        assert "DTMF" not in channel.handlers

    async def test_channel_update_state_from_event(self, channel):
        event = ESLEvent({
            "Channel-State-Number": "4",
            "Channel-Call-State": "ACTIVE",
            "variable_caller_id_name": "Test User"
        })
        
        channel.update_state(event)
        
        assert channel.state == ChannelState.EXECUTE
        assert channel.call_state == CallState.ACTIVE
        assert channel.variables["caller_id_name"] == "Test User"

    async def test_channel_bridge_to_dialstring(self, channel, mock_session):
        bleg_uuid = str(uuid4())
        mock_result = CommandResult(ESLEvent(), channel=channel)
        
        with patch('genesis.channel.uuid4', return_value=bleg_uuid):
            channel.session.sendmsg.return_value = mock_result
            
            result, bleg_channel = await channel.bridge("user/1000")
            
            assert isinstance(bleg_channel, Channel)
            assert bleg_channel.uuid == bleg_uuid
            assert bleg_channel in mock_session.channels.values()

    async def test_channel_bridge_to_existing_channel(self, channel, background_job_result_factory):
        target_channel = Channel(str(uuid4()), channel.session)
    
        # Mock the BackgroundJobResult that bgapi_execute returns.
        mock_bg_result = background_job_result_factory(is_successful=True)
    
        # session.bgapi_execute is an async method that returns the awaitable result
        channel.session.bgapi_execute = AsyncMock(return_value=mock_bg_result)
    
        # Act
        result = await channel.bridge(target_channel)
    
        # Assert
        channel.session.bgapi_execute.assert_called_once_with(
            f"uuid_bridge {channel.uuid} {target_channel.uuid}"
        )
    
        assert result is mock_bg_result
    
        # The caller would then await this result
        awaited_result = await result
        assert awaited_result is mock_bg_result
        assert awaited_result.is_successful

    async def test_channel_originate_success(self, mock_session, background_job_result_factory):
        new_uuid = str(uuid4())
    
        # Mock the BackgroundJobResult that bgapi_execute returns
        mock_bg_result = background_job_result_factory(
            is_successful=True,
            response="+OK some-uuid"
        )
    
        # Mock session.bgapi_execute, which is what Channel.originate uses
        mock_session.bgapi_execute = AsyncMock(return_value=mock_bg_result)
    
        with patch('genesis.channel.uuid4', return_value=new_uuid):
            channel = await Channel.originate(
                session=mock_session,
                destination="user/1000"
            )
    
            assert channel.uuid == new_uuid
            assert new_uuid in mock_session.channels
            mock_session.bgapi_execute.assert_called_once()

    async def test_channel_originate_failure(self, mock_session, background_job_result_factory):
        # Mock bgapi_execute to return a failed result
        mock_bg_result = background_job_result_factory(
            is_successful=False,
            response="-ERR INVALID_DESTINATION"
        )
    
        mock_session.bgapi_execute = AsyncMock(return_value=mock_bg_result)
    
        with pytest.raises(OriginateError):
            await Channel.originate(
                session=mock_session,
                destination="invalid/destination"
            )

    async def test_channel_playback(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.playback("/tmp/test.wav")
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="playback",
            data="/tmp/test.wav",
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )

    async def test_channel_silence(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.silence(2000)
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="playback",
            data="silence_stream://2000",
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )

    async def test_channel_set_variable(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.set_variable("test_var", "test_value")
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="set",
            data="test_var=test_value",
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )

    async def test_channel_get_variable_local(self, channel):
        channel.variables["test_var"] = "test_value"
        
        result = await channel.get_variable("test_var")
        
        assert result == "test_value"

    async def test_channel_get_variable_not_found(self, channel):
        result = await channel.get_variable("nonexistent")
        
        assert result is None

    async def test_channel_unbridge(self, channel, background_job_result_factory):
        # Mock the BackgroundJobResult that bgapi_execute returns
        mock_bg_result = background_job_result_factory(is_successful=True)
    
        # session.bgapi_execute is an async method that returns the awaitable result
        channel.session.bgapi_execute = AsyncMock(return_value=mock_bg_result)
    
        # Act
        result = await channel.unbridge(destination="1000", park=False)
    
        # Assert
        expected_cmd = f"uuid_transfer {channel.uuid}  1000 inline"
        channel.session.bgapi_execute.assert_called_once_with(expected_cmd)
    
        assert result is mock_bg_result
    
        # Await the result and check properties
        awaited_result = await result
        assert awaited_result is mock_bg_result
        assert awaited_result.is_successful

    async def test_channel_answer(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.answer()
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="answer",
            data=None,
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )

    async def test_channel_park(self, channel):
        mock_result = CommandResult(ESLEvent(), channel=channel)
        channel.session.sendmsg.return_value = mock_result
        
        result = await channel.park()
        
        channel.session.sendmsg.assert_called_once_with(
            command="execute",
            application="park",
            data=None,
            lock=False,
            uuid=channel.uuid,
            app_event_uuid=None,
            headers=None
        )
