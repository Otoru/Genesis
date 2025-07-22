import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from genesis.session import Session
from genesis.events import ESLEvent
from genesis.channel import Channel
from genesis.results import CommandResult
from genesis.exceptions import OperationInterruptedException


class TestSession:
    @pytest.fixture
    def mock_reader(self):
        return AsyncMock()

    @pytest.fixture
    def mock_writer(self):
        writer = AsyncMock()
        writer.get_extra_info.return_value = ('127.0.0.1', 12345)
        return writer

    @pytest.fixture
    def session(self, mock_reader, mock_writer):
        return Session(mock_reader, mock_writer)

    async def test_session_initialization(self, session, mock_reader, mock_writer):
        assert session.reader == mock_reader
        assert session.writer == mock_writer
        assert session.context == {}
        assert session.channels == {}
        assert session.channel_a is None
        assert not session.myevents
        assert session.linger

    async def test_session_dispatch_creates_channel_on_connect(self, session):
        connect_event = ESLEvent({
            "Content-Type": "command/reply",
            "Channel-State": "CS_EXECUTE",
            "Unique-ID": "test-uuid-123"
        })
        
        await session._dispatch_event_to_channels(connect_event)
        
        assert "test-uuid-123" in session.channels
        assert session.channel_a is not None
        assert session.channel_a.uuid == "test-uuid-123"

    async def test_session_dispatch_creates_channel_on_channel_create(self, session):
        create_event = ESLEvent({
            "Event-Name": "CHANNEL_CREATE",
            "Unique-ID": "test-uuid-456"
        })
        
        await session._dispatch_event_to_channels(create_event)
        
        assert "test-uuid-456" in session.channels

    async def test_session_dispatch_removes_channel_on_destroy(self, session):
        # First create a channel
        create_event = ESLEvent({
            "Event-Name": "CHANNEL_CREATE", 
            "Unique-ID": "test-uuid-789"
        })
        await session._dispatch_event_to_channels(create_event)
        
        # Then destroy it
        destroy_event = ESLEvent({
            "Event-Name": "CHANNEL_DESTROY",
            "Unique-ID": "test-uuid-789"
        })
        await session._dispatch_event_to_channels(destroy_event)
        
        assert "test-uuid-789" not in session.channels

    async def test_session_sendmsg_execute_blocking(self, session):
        session.send = AsyncMock(return_value=ESLEvent({"Reply-Text": "+OK"}))
        
        with patch.object(session, '_awaitable_complete_command') as mock_awaitable:
            mock_event = AsyncMock()
            mock_awaitable.return_value = mock_event
            
            result = await session.sendmsg(
                command="execute",
                application="playback", 
                data="/tmp/test.wav"
            )
            
            mock_awaitable.assert_called_once()
            mock_event.wait.assert_called_once()
            assert isinstance(result, CommandResult)


    async def test_session_answer(self, session):
        session.sendmsg = AsyncMock()
        
        await session.answer()
        
        session.sendmsg.assert_called_once_with("execute", "answer")

    async def test_session_park(self, session):
        session.sendmsg = AsyncMock()
        
        await session.park()
        
        session.sendmsg.assert_called_once_with("execute", "park")

    async def test_session_hangup(self, session):
        session.sendmsg = AsyncMock()
        
        await session.hangup("BUSY")
        
        session.sendmsg.assert_called_once_with("execute", "hangup", "BUSY")

    async def test_session_playback(self, session):
        session.sendmsg = AsyncMock()
        
        await session.playback("/tmp/test.wav")
        
        session.sendmsg.assert_called_once_with(
            "execute", "playback", "/tmp/test.wav"
        )

    async def test_session_bridge_delegates_to_channel(self, session):
        # Create a mock channel
        mock_channel = AsyncMock(spec=Channel)
        mock_channel.uuid = "test-uuid"
        mock_channel.is_gone = False
        mock_result = CommandResult(ESLEvent())
        mock_bleg = Channel("bleg-uuid", session)
        mock_channel.bridge.return_value = (mock_result, mock_bleg)
        
        result, bleg = await session.bridge(
            mock_channel, 
            "user/1000",
            call_variables={"test": "value"}
        )
        
        mock_channel.bridge.assert_called_once_with(
            "user/1000", 
            {"test": "value"}
        )
        assert result == mock_result
        assert bleg == mock_bleg

    async def test_session_originate_delegates_to_channel(self, session):
        mock_channel = Channel("new-uuid", session)
        
        with patch.object(Channel, 'originate', return_value=mock_channel) as mock_originate:
            result = await session.originate("user/1000")
            
            mock_originate.assert_called_once_with(
                session=session,
                destination="user/1000",
                uuid=None,
                variables=None,
                timeout=None,
                application_after="park"
            )
            assert result == mock_channel

    async def test_session_log(self, session):
        session.sendmsg = AsyncMock()
        
        await session.log("INFO", "Test message")
        
        session.sendmsg.assert_called_once_with("execute", "log", "INFO Test message")

    async def test_session_say(self, session):
        session.sendmsg = AsyncMock()
        
        await session.say("123", module="en", lang="us")
        
        expected_args = "en:us NUMBER pronounced FEMININE 123"
        session.sendmsg.assert_called_once_with("execute", "say", expected_args)

    async def test_session_play_and_get_digits(self, session):
        session.sendmsg = AsyncMock()
        
        await session.play_and_get_digits(
            tries=3,
            timeout=5000,
            terminators="#",
            file="/tmp/prompt.wav",
            minimal=1,
            maximum=10
        )
        
        session.sendmsg.assert_called_once()
        args = session.sendmsg.call_args[0]
        assert args[0] == "execute"
        assert args[1] == "play_and_get_digits"

    async def test_session_dispatch_ignores_events_without_uuid(self, session):
        event = ESLEvent({
            "Event-Name": "HEARTBEAT",
            "Core-UUID": "system-uuid"
        })
        
        # Should not raise any exceptions or create channels
        await session._dispatch_event_to_channels(event)
        
        assert len(session.channels) == 0
        assert session.channel_a is None
