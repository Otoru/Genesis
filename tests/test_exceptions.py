"""
Tests for the exceptions module.
"""

import pytest

from genesis.exceptions import (
    AuthenticationError,
    ConnectionError,
    ConnectionTimeoutError,
    OperationInterruptedException,
    OriginateError,
    SessionGoneAway,
    UnconnectedError,
)


class TestExistingExceptions:
    """Tests for existing exceptions to ensure backwards compatibility."""

    def test_connection_error_is_exception(self) -> None:
        """Test that ConnectionError is an exception."""
        with pytest.raises(ConnectionError):
            raise ConnectionError("Connection failed")

    def test_connection_timeout_error_inherits_connection_error(self) -> None:
        """Test that ConnectionTimeoutError inherits from ConnectionError."""
        assert issubclass(ConnectionTimeoutError, ConnectionError)

    def test_session_gone_away(self) -> None:
        """Test SessionGoneAway exception."""
        with pytest.raises(SessionGoneAway):
            raise SessionGoneAway("Session ended")

    def test_authentication_error_inherits_value_error(self) -> None:
        """Test that AuthenticationError inherits from ValueError."""
        assert issubclass(AuthenticationError, ValueError)

    def test_unconnected_error(self) -> None:
        """Test UnconnectedError exception."""
        with pytest.raises(UnconnectedError):
            raise UnconnectedError("Not connected")


class TestOperationInterruptedException:
    """Tests for OperationInterruptedException."""

    def test_basic_instantiation(self) -> None:
        """Test basic instantiation with only message."""
        exc = OperationInterruptedException("Playback interrupted")
        assert str(exc) == "Playback interrupted"
        assert exc.event_uuid is None
        assert exc.channel_uuid is None

    def test_with_event_uuid(self) -> None:
        """Test instantiation with event_uuid."""
        exc = OperationInterruptedException("Interrupted", event_uuid="event-123")
        assert exc.event_uuid == "event-123"
        assert exc.channel_uuid is None

    def test_with_channel_uuid(self) -> None:
        """Test instantiation with channel_uuid."""
        exc = OperationInterruptedException("Interrupted", channel_uuid="channel-456")
        assert exc.event_uuid is None
        assert exc.channel_uuid == "channel-456"

    def test_with_both_uuids(self) -> None:
        """Test instantiation with both UUIDs."""
        exc = OperationInterruptedException(
            "Interrupted",
            event_uuid="event-123",
            channel_uuid="channel-456",
        )
        assert exc.event_uuid == "event-123"
        assert exc.channel_uuid == "channel-456"

    def test_is_exception(self) -> None:
        """Test that it can be raised and caught."""
        with pytest.raises(OperationInterruptedException) as exc_info:
            raise OperationInterruptedException(
                "Test", event_uuid="e1", channel_uuid="c1"
            )
        assert exc_info.value.event_uuid == "e1"
        assert exc_info.value.channel_uuid == "c1"


class TestOriginateError:
    """Tests for OriginateError."""

    def test_basic_instantiation(self) -> None:
        """Test basic instantiation with message and destination."""
        exc = OriginateError(
            "Failed to originate", destination="sofia/gateway/gw1/1234"
        )
        assert str(exc) == "Failed to originate"
        assert exc.destination == "sofia/gateway/gw1/1234"
        assert exc.variables == {}

    def test_with_variables(self) -> None:
        """Test instantiation with variables."""
        variables = {"caller_id_name": "Test", "timeout": "30"}
        exc = OriginateError(
            "Failed",
            destination="sofia/internal/1000",
            variables=variables,
        )
        assert exc.destination == "sofia/internal/1000"
        assert exc.variables == variables

    def test_variables_default_to_empty_dict(self) -> None:
        """Test that variables default to empty dict when None."""
        exc = OriginateError("Failed", destination="test", variables=None)
        assert exc.variables == {}
        assert isinstance(exc.variables, dict)

    def test_is_exception(self) -> None:
        """Test that it can be raised and caught."""
        with pytest.raises(OriginateError) as exc_info:
            raise OriginateError(
                "Originate failed",
                destination="sofia/gw/test",
                variables={"key": "value"},
            )
        assert exc_info.value.destination == "sofia/gw/test"
        assert exc_info.value.variables == {"key": "value"}
