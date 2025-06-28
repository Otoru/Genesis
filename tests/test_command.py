import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from genesis.command import CommandResult
from genesis.events import ESLEvent
from genesis.channel import Channel


class TestCommandResult:
    @pytest.fixture
    def mock_channel(self):
        channel = AsyncMock(spec=Channel)
        channel.uuid = "test-uuid-123"
        return channel

    @pytest.fixture
    def initial_event(self):
        return ESLEvent({"Reply-Text": "+OK"})

    def test_command_result_initialization(self, initial_event, mock_channel):
        result = CommandResult(
            initial_event=initial_event,
            app_uuid="app-123",
            channel_uuid="chan-123", 
            channel=mock_channel,
            command="execute",
            application="playback",
            data="/tmp/test.wav"
        )
        
        assert result.initial_event == initial_event
        assert result.app_uuid == "app-123"
        assert result.channel_uuid == "chan-123"
        assert result.channel == mock_channel
        assert result.command == "execute"
        assert result.application == "playback"
        assert result.data == "/tmp/test.wav"
        assert not result.is_completed

    def test_command_result_already_complete_on_init(self):
        complete_event = ESLEvent({
            "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
            "Application-UUID": "app-123"
        })
        
        result = CommandResult(
            initial_event=complete_event,
            app_uuid="app-123"
        )
        
        assert result.is_completed
        assert result.complete_event == complete_event

    def test_command_result_set_complete(self, initial_event):
        result = CommandResult(initial_event)
        complete_event = ESLEvent({"Application-Response": "SUCCESS"})
        
        result.set_complete(complete_event)
        
        assert result.is_completed
        assert result.complete_event == complete_event
        assert result.response == "SUCCESS"

    def test_command_result_set_exception(self, initial_event):
        result = CommandResult(initial_event)
        exception = Exception("Test error")
        
        result.set_exception(exception)
        
        assert result.is_completed
        assert result.exception == exception

    def test_command_result_is_successful_when_complete(self, initial_event):
        result = CommandResult(initial_event)
        result.set_complete(ESLEvent())
        
        assert result.is_successful

    def test_command_result_is_successful_raises_when_not_complete(self, initial_event):
        result = CommandResult(initial_event)
        
        with pytest.raises(ValueError):
            result.is_successful

    def test_command_result_bool_conversion(self, initial_event):
        result = CommandResult(initial_event)
        
        assert not bool(result)
        
        result.set_complete(ESLEvent())
        
        assert bool(result)

    async def test_command_result_wait_success(self, initial_event):
        result = CommandResult(initial_event)
        
        # Simulate completion in background
        async def complete_later():
            await asyncio.sleep(0.01)
            result.set_complete(ESLEvent())
        
        asyncio.create_task(complete_later())
        
        completed_result = await result.wait()
        
        assert completed_result == result
        assert result.is_completed

    async def test_command_result_wait_with_exception(self, initial_event):
        result = CommandResult(initial_event)
        test_exception = Exception("Test error")
        
        # Simulate exception in background
        async def fail_later():
            await asyncio.sleep(0.01)
            result.set_exception(test_exception)
        
        asyncio.create_task(fail_later())
        
        with pytest.raises(Exception) as exc_info:
            await result.wait()
        
        assert exc_info.value == test_exception

    async def test_command_result_awaitable(self, initial_event):
        result = CommandResult(initial_event)
        
        # Simulate completion in background
        async def complete_later():
            await asyncio.sleep(0.01)
            result.set_complete(ESLEvent())
        
        asyncio.create_task(complete_later())
        
        # Test direct await
        completed_result = await result
        
        assert completed_result == result
        assert result.is_completed

    def test_command_result_response_when_not_complete(self, initial_event):
        result = CommandResult(initial_event)
        
        assert result.response is None

    def test_command_result_response_when_complete_no_response(self, initial_event):
        result = CommandResult(initial_event)
        complete_event = ESLEvent({})
        result.set_complete(complete_event)
        
        assert result.response is None
