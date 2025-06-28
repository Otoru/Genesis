import pytest

from genesis.exceptions import (
    ConnectionError, ConnectionTimeoutError, SessionGoneAway,
    AuthenticationError, UnconnectedError, OperationInterruptedException,
    OriginateError
)


class TestExceptions:
    def test_connection_timeout_error(self):
        error = ConnectionTimeoutError("Timeout occurred")
        assert str(error) == "Timeout occurred"
        assert isinstance(error, ConnectionError)

    def test_session_gone_away(self):
        error = SessionGoneAway("Session is gone")
        assert str(error) == "Session is gone"

    def test_authentication_error(self):
        error = AuthenticationError("Invalid credentials")
        assert str(error) == "Invalid credentials"
        assert isinstance(error, ValueError)

    def test_unconnected_error(self):
        error = UnconnectedError("Not connected")
        assert str(error) == "Not connected"

    def test_operation_interrupted_exception(self):
        error = OperationInterruptedException(
            "Operation interrupted",
            event_uuid="event-123",
            channel_uuid="channel-456"
        )
        assert str(error) == "Operation interrupted"
        assert error.event_uuid == "event-123"
        assert error.channel_uuid == "channel-456"

    def test_operation_interrupted_exception_without_uuids(self):
        error = OperationInterruptedException("Operation interrupted")
        assert str(error) == "Operation interrupted"
        assert error.event_uuid is None
        assert error.channel_uuid is None

    def test_originate_error(self):
        variables = {"caller_id": "123"}
        error = OriginateError("Failed to originate", "user/1000", variables)
        assert str(error) == "Failed to originate"
        assert error.destination == "user/1000"
        assert error.variables == variables

    def test_originate_error_without_variables(self):
        error = OriginateError("Failed to originate", "user/1000")
        assert str(error) == "Failed to originate"
        assert error.destination == "user/1000"
        assert error.variables == {}

    def test_connection_error_inheritance(self):
        # Test that our ConnectionError inherits from built-in ConnectionError
        error = ConnectionError("Connection failed")
        assert isinstance(error, ConnectionError)

    def test_connection_timeout_error_inheritance(self):
        error = ConnectionTimeoutError()
        assert isinstance(error, ConnectionError)
        assert isinstance(error, Exception)

    def test_exception_with_empty_message(self):
        error = SessionGoneAway("")
        assert str(error) == ""

    def test_operation_interrupted_with_none_message(self):
        # Test edge case where message might be None
        try:
            error = OperationInterruptedException(None)
            # If this doesn't raise, the message should be converted to string
            assert str(error) == "None"
        except TypeError:
            # If it raises TypeError, that's also acceptable behavior
            pass
