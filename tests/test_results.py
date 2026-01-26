"""
Tests for the genesis.channels.results module.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from genesis.channels.results import (
    AwaitableResult,
    BackgroundJobResult,
    CommandResult,
)
from genesis.parser import ESLEvent as MockEvent


class TestAwaitableResult:
    """Tests for the base AwaitableResult class."""

    def test_initial_state(self) -> None:
        """Test that a new result is not completed."""
        result = AwaitableResult()
        assert not result.is_completed
        assert result.completion_event is None
        assert result.exception is None

    def test_bool_when_not_complete(self) -> None:
        """Test bool conversion when not complete."""
        result = AwaitableResult()
        assert not bool(result)

    def test_bool_when_complete(self) -> None:
        """Test bool conversion when complete."""
        result = AwaitableResult()
        result.set_complete({})
        assert bool(result)

    def test_set_complete(self) -> None:
        """Test marking result as complete."""
        result = AwaitableResult()
        event = {"Event-Name": "TEST"}
        result.set_complete(event)
        assert result.is_completed
        assert result.completion_event == event

    def test_set_exception(self) -> None:
        """Test marking result as failed."""
        result = AwaitableResult()
        exc = ValueError("test error")
        result.set_exception(exc)
        assert result.is_completed
        assert result.exception == exc

    def test_is_successful_when_complete_no_exception(self) -> None:
        """Test is_successful returns True when completed without exception."""
        result = AwaitableResult()
        result.set_complete({})
        assert result.is_successful

    def test_is_successful_when_exception(self) -> None:
        """Test is_successful returns False when exception occurred."""
        result = AwaitableResult()
        result.set_exception(ValueError("error"))
        assert not result.is_successful

    def test_is_successful_raises_when_not_complete(self) -> None:
        """Test is_successful raises when not yet complete."""
        result = AwaitableResult()
        with pytest.raises(ValueError, match="Operation has not completed yet"):
            _ = result.is_successful

    def test_response_raises_not_implemented(self) -> None:
        """Test that response property must be implemented by subclasses."""
        result = AwaitableResult()
        with pytest.raises(NotImplementedError):
            _ = result.response

    async def test_wait_success(self) -> None:
        """Test waiting for successful completion."""
        result = AwaitableResult()

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            result.set_complete({})

        asyncio.create_task(complete_later())
        awaited = await result.wait()
        assert awaited == result
        assert result.is_completed

    async def test_wait_raises_exception(self) -> None:
        """Test that wait raises the stored exception."""
        result = AwaitableResult()
        test_exc = RuntimeError("test failure")

        async def fail_later() -> None:
            await asyncio.sleep(0.01)
            result.set_exception(test_exc)

        asyncio.create_task(fail_later())
        with pytest.raises(RuntimeError, match="test failure"):
            await result.wait()

    async def test_direct_await(self) -> None:
        """Test that result can be awaited directly."""
        result = AwaitableResult()

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            result.set_complete({})

        asyncio.create_task(complete_later())
        awaited = await result
        assert awaited == result


class TestCommandResult:
    """Tests for CommandResult class."""

    @pytest.fixture
    def mock_channel(self) -> MagicMock:
        """Create a mock channel."""
        channel = MagicMock()
        channel.uuid = "test-uuid-123"
        channel.on = MagicMock()
        channel.remove = MagicMock()
        return channel

    @pytest.fixture
    def initial_event(self) -> MockEvent:
        """Create an initial event."""
        return MockEvent({"Reply-Text": "+OK"})

    def test_initialization(
        self, initial_event: MockEvent, mock_channel: MagicMock
    ) -> None:
        """Test CommandResult initialization."""
        result = CommandResult(
            initial_event=initial_event,
            app_uuid="app-123",
            channel_uuid="chan-123",
            channel=mock_channel,
            command="execute",
            application="playback",
            data="/tmp/test.wav",
        )

        assert result.initial_event == initial_event
        assert result.app_uuid == "app-123"
        assert result.channel_uuid == "chan-123"
        assert result.channel == mock_channel
        assert result.command == "execute"
        assert result.application == "playback"
        assert result.data == "/tmp/test.wav"
        assert not result.is_completed

    def test_already_complete_on_init(self) -> None:
        """Test that result is marked complete if initial event is completion."""
        completion_event = MockEvent(
            {
                "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
                "Application-UUID": "app-123",
            }
        )

        result = CommandResult(
            initial_event=completion_event,
            app_uuid="app-123",
        )

        assert result.is_completed
        assert result.completion_event == completion_event

    def test_set_complete(self, initial_event: MockEvent) -> None:
        """Test setting completion."""
        result = CommandResult(initial_event)
        completion_event = MockEvent({"Application-Response": "SUCCESS"})
        result.set_complete(completion_event)

        assert result.is_completed
        assert result.completion_event == completion_event
        assert result.response == "SUCCESS"

    def test_set_exception(self, initial_event: MockEvent) -> None:
        """Test setting exception."""
        result = CommandResult(initial_event)
        exception = Exception("Test error")
        result.set_exception(exception)

        assert result.is_completed
        assert result.exception == exception

    def test_is_successful_execute_ok(self, initial_event: MockEvent) -> None:
        """Test is_successful for successful execute command."""
        result = CommandResult(initial_event, command="execute")
        result.set_complete(MockEvent({"Application-Response": "FILE PLAYED"}))
        assert result.is_successful

    def test_is_successful_execute_error(self, initial_event: MockEvent) -> None:
        """Test is_successful for failed execute command."""
        result = CommandResult(initial_event, command="execute")
        result.set_complete(MockEvent({"Application-Response": "-ERR file not found"}))
        assert not result.is_successful

    def test_is_successful_other_command_ok(self, initial_event: MockEvent) -> None:
        """Test is_successful for successful non-execute command."""
        result = CommandResult(initial_event, command="hangup")
        result.set_complete(MockEvent({"Reply-Text": "+OK"}))
        assert result.is_successful

    def test_is_successful_other_command_error(self, initial_event: MockEvent) -> None:
        """Test is_successful for failed non-execute command."""
        result = CommandResult(initial_event, command="hangup")
        result.set_complete(MockEvent({"Reply-Text": "-ERR"}))
        assert not result.is_successful

    def test_is_successful_raises_if_not_complete(
        self, initial_event: MockEvent
    ) -> None:
        """Test is_successful raises when not complete."""
        result = CommandResult(initial_event)
        with pytest.raises(ValueError, match="Operation has not completed yet"):
            _ = result.is_successful

    def test_response_when_not_complete(self, initial_event: MockEvent) -> None:
        """Test response returns None when not complete."""
        result = CommandResult(initial_event)
        assert result.response is None

    def test_response_when_complete(self, initial_event: MockEvent) -> None:
        """Test response returns Application-Response when complete."""
        result = CommandResult(initial_event)
        result.set_complete(MockEvent({"Application-Response": "test response"}))
        assert result.response == "test response"

    def test_bool_conversion(self, initial_event: MockEvent) -> None:
        """Test bool conversion."""
        result = CommandResult(initial_event)
        assert not bool(result)
        result.set_complete(MockEvent())
        assert bool(result)

    async def test_wait_success(self, initial_event: MockEvent) -> None:
        """Test waiting for success."""
        result = CommandResult(initial_event)

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            result.set_complete(MockEvent())

        asyncio.create_task(complete_later())
        completed = await result.wait()
        assert completed == result
        assert result.is_completed

    async def test_wait_with_exception(self, initial_event: MockEvent) -> None:
        """Test waiting when exception occurs."""
        result = CommandResult(initial_event)
        test_exc = Exception("Test error")

        async def fail_later() -> None:
            await asyncio.sleep(0.01)
            result.set_exception(test_exc)

        asyncio.create_task(fail_later())
        with pytest.raises(Exception, match="Test error"):
            await result.wait()

    async def test_direct_await(self, initial_event: MockEvent) -> None:
        """Test direct await."""
        result = CommandResult(initial_event)

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            result.set_complete(MockEvent())

        asyncio.create_task(complete_later())
        completed = await result
        assert completed == result


class TestBackgroundJobResult:
    """Tests for BackgroundJobResult class."""

    def test_initialization(self) -> None:
        """Test initialization."""
        result = BackgroundJobResult(job_uuid="job-123", command="test_cmd")
        assert result.job_uuid == "job-123"
        assert result.command == "test_cmd"
        assert not result.is_completed

    def test_set_complete(self) -> None:
        """Test setting completion with body."""
        result = BackgroundJobResult("job-123", "test_cmd")
        event = MockEvent()
        event.body = "+OK SUCCESS"
        result.set_complete(event)

        assert result.is_completed
        assert result.completion_event == event
        assert result.response == "+OK SUCCESS"

    def test_is_successful_ok(self) -> None:
        """Test is_successful when response starts with +OK."""
        result = BackgroundJobResult("job-1", "cmd")
        event = MockEvent()
        event.body = "+OK job done"
        result.set_complete(event)
        assert result.is_successful

    def test_is_successful_err(self) -> None:
        """Test is_successful when response starts with -ERR."""
        result = BackgroundJobResult("job-2", "cmd")
        event = MockEvent()
        event.body = "-ERR something went wrong"
        result.set_complete(event)
        assert not result.is_successful

    def test_is_successful_other_response(self) -> None:
        """Test is_successful for non-standard response."""
        result = BackgroundJobResult("job-3", "cmd")
        event = MockEvent()
        event.body = "some other response"
        result.set_complete(event)
        assert not result.is_successful

    def test_is_successful_with_exception(self) -> None:
        """Test is_successful when exception occurred."""
        result = BackgroundJobResult("job-4", "cmd")
        result.set_exception(Exception("error"))
        assert not result.is_successful

    def test_is_successful_raises_if_not_complete(self) -> None:
        """Test is_successful raises when not complete."""
        result = BackgroundJobResult("job-5", "cmd")
        with pytest.raises(ValueError, match="Operation has not completed yet"):
            _ = result.is_successful

    def test_set_exception(self) -> None:
        """Test setting exception."""
        result = BackgroundJobResult("job-123", "test_cmd")
        exception = RuntimeError("Job failed")
        result.set_exception(exception)

        assert result.is_completed
        assert not result.is_successful
        assert result.exception == exception

    def test_response_when_not_complete(self) -> None:
        """Test response returns None when not complete."""
        result = BackgroundJobResult("job-123", "cmd")
        assert result.response is None

    async def test_awaitable_success(self) -> None:
        """Test awaiting successful job."""
        result = BackgroundJobResult("job-123", "test_cmd")

        async def complete_later() -> None:
            await asyncio.sleep(0.01)
            event = MockEvent()
            event.body = "+OK Done"
            result.set_complete(event)

        asyncio.create_task(complete_later())
        completed = await result

        assert completed.is_completed
        assert completed.is_successful
        assert completed.response == "+OK Done"

    async def test_awaitable_failure(self) -> None:
        """Test awaiting failed job."""
        result = BackgroundJobResult("job-123", "test_cmd")
        test_exc = ValueError("Something went wrong")

        async def fail_later() -> None:
            await asyncio.sleep(0.01)
            result.set_exception(test_exc)

        asyncio.create_task(fail_later())
        with pytest.raises(ValueError, match="Something went wrong"):
            await result
