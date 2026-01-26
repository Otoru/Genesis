"""
Tests for the genesis.channels.bgapi module.
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from genesis.channels.bgapi import BackgroundAPI
from genesis.channels.results import BackgroundJobResult
from genesis.exceptions import ConnectionError, UnconnectedError
from genesis.parser import ESLEvent


class TestBackgroundAPI:
    """Tests for BackgroundAPI class."""

    @pytest.fixture
    def mock_protocol(self) -> MagicMock:
        """Create a mock protocol."""
        protocol = MagicMock()
        protocol.is_connected = True
        protocol.writer = MagicMock()
        protocol.writer.is_closing.return_value = False
        protocol.on = MagicMock()
        protocol.remove = MagicMock()
        protocol.send = AsyncMock()
        return protocol

    def test_initialization(self, mock_protocol: MagicMock) -> None:
        """Test BackgroundAPI initialization."""
        bgapi = BackgroundAPI(mock_protocol)
        assert bgapi.protocol == mock_protocol
        assert bgapi._pending_jobs == {}
        assert bgapi._handler_registered is False

    def test_ensure_handler_registered(self, mock_protocol: MagicMock) -> None:
        """Test handler registration."""
        bgapi = BackgroundAPI(mock_protocol)
        bgapi._ensure_handler_registered()

        mock_protocol.on.assert_called_once_with(
            "BACKGROUND_JOB", bgapi._handle_background_job
        )
        assert bgapi._handler_registered is True

        # Second call should not register again
        bgapi._ensure_handler_registered()
        assert mock_protocol.on.call_count == 1

    async def test_execute_not_connected(self, mock_protocol: MagicMock) -> None:
        """Test execute raises when not connected."""
        mock_protocol.is_connected = False
        bgapi = BackgroundAPI(mock_protocol)

        with pytest.raises(UnconnectedError):
            await bgapi.execute("status")

    async def test_execute_writer_closing(self, mock_protocol: MagicMock) -> None:
        """Test execute raises when writer is closing."""
        mock_protocol.writer.is_closing.return_value = True
        bgapi = BackgroundAPI(mock_protocol)

        with pytest.raises(ConnectionError):
            await bgapi.execute("status")

    async def test_execute_success(self, mock_protocol: MagicMock) -> None:
        """Test successful bgapi execution."""
        # Mock the send response for the bgapi command
        mock_protocol.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "+OK Job-UUID: test-job-123"})
        )

        bgapi = BackgroundAPI(mock_protocol)
        result = await bgapi.execute("status", job_uuid="test-job-123")

        assert isinstance(result, BackgroundJobResult)
        assert result.job_uuid == "test-job-123"
        assert result.command == "status"
        assert "test-job-123" in bgapi._pending_jobs

    async def test_execute_generates_uuid(self, mock_protocol: MagicMock) -> None:
        """Test that execute generates a UUID if not provided."""
        mock_protocol.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "+OK Job-UUID: generated-uuid"})
        )

        bgapi = BackgroundAPI(mock_protocol)

        with patch("genesis.channels.bgapi.uuid4") as mock_uuid:
            mock_uuid.return_value = MagicMock(__str__=lambda self: "generated-uuid")
            result = await bgapi.execute("status")

        assert result.job_uuid == "generated-uuid"

    async def test_execute_failed_response(self, mock_protocol: MagicMock) -> None:
        """Test handling of failed bgapi response."""
        mock_protocol.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "-ERR command not found"})
        )

        bgapi = BackgroundAPI(mock_protocol)
        result = await bgapi.execute("invalid_command", job_uuid="job-123")

        assert result.is_completed
        assert result.exception is not None
        assert "job-123" not in bgapi._pending_jobs

    async def test_execute_uuid_mismatch(self, mock_protocol: MagicMock) -> None:
        """Test handling when FreeSWITCH returns different UUID."""
        mock_protocol.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "+OK Job-UUID: different-uuid"})
        )

        bgapi = BackgroundAPI(mock_protocol)
        result = await bgapi.execute("status", job_uuid="original-uuid")

        # Should use the UUID returned by FreeSWITCH
        assert result.job_uuid == "different-uuid"
        assert "different-uuid" in bgapi._pending_jobs
        assert "original-uuid" not in bgapi._pending_jobs

    async def test_handle_background_job(self, mock_protocol: MagicMock) -> None:
        """Test handling of BACKGROUND_JOB event."""
        mock_protocol.send = AsyncMock(
            return_value=ESLEvent({"Reply-Text": "+OK Job-UUID: job-123"})
        )

        bgapi = BackgroundAPI(mock_protocol)
        result = await bgapi.execute("status", job_uuid="job-123")

        assert not result.is_completed

        # Simulate receiving the BACKGROUND_JOB event
        event = ESLEvent({"Job-UUID": "job-123"})
        event.body = "+OK status output"
        await bgapi._handle_background_job(event)

        assert result.is_completed
        assert result.response == "+OK status output"
        assert "job-123" not in bgapi._pending_jobs

    async def test_handle_background_job_no_uuid(
        self, mock_protocol: MagicMock
    ) -> None:
        """Test handling of BACKGROUND_JOB event without UUID."""
        bgapi = BackgroundAPI(mock_protocol)

        # Should not raise, just log warning
        await bgapi._handle_background_job(ESLEvent({}))

    async def test_handle_background_job_unknown_uuid(
        self, mock_protocol: MagicMock
    ) -> None:
        """Test handling of BACKGROUND_JOB event for unknown job."""
        bgapi = BackgroundAPI(mock_protocol)

        # Should not raise, just log debug message
        await bgapi._handle_background_job(ESLEvent({"Job-UUID": "unknown-job"}))

    def test_get_pending_jobs(self, mock_protocol: MagicMock) -> None:
        """Test get_pending_jobs returns copy."""
        bgapi = BackgroundAPI(mock_protocol)
        result = BackgroundJobResult("job-1", "cmd")
        bgapi._pending_jobs["job-1"] = result

        pending = bgapi.get_pending_jobs()
        assert pending == {"job-1": result}
        # Verify it's a copy
        pending["job-2"] = BackgroundJobResult("job-2", "cmd")
        assert "job-2" not in bgapi._pending_jobs

    def test_delete_job(self, mock_protocol: MagicMock) -> None:
        """Test _delete_job removes job from tracking."""
        bgapi = BackgroundAPI(mock_protocol)
        result = BackgroundJobResult("job-1", "cmd")
        bgapi._pending_jobs["job-1"] = result

        assert bgapi._delete_job("job-1") is True
        assert "job-1" not in bgapi._pending_jobs

        # Non-existent job returns False
        assert bgapi._delete_job("non-existent") is False

    def test_cleanup(self, mock_protocol: MagicMock) -> None:
        """Test cleanup cancels pending jobs and removes handler."""
        bgapi = BackgroundAPI(mock_protocol)
        bgapi._handler_registered = True

        result1 = BackgroundJobResult("job-1", "cmd1")
        result2 = BackgroundJobResult("job-2", "cmd2")
        bgapi._pending_jobs = {"job-1": result1, "job-2": result2}

        bgapi.cleanup()

        # Both jobs should be cancelled with exceptions
        assert result1.is_completed
        assert result1.exception is not None
        assert result2.is_completed
        assert result2.exception is not None

        # Pending jobs should be cleared
        assert bgapi._pending_jobs == {}

        # Handler should be removed
        mock_protocol.remove.assert_called_once_with(
            "BACKGROUND_JOB", bgapi._handle_background_job
        )
        assert bgapi._handler_registered is False

    def test_cleanup_when_not_registered(self, mock_protocol: MagicMock) -> None:
        """Test cleanup when handler not registered."""
        bgapi = BackgroundAPI(mock_protocol)

        # Should not raise
        bgapi.cleanup()

        mock_protocol.remove.assert_not_called()
