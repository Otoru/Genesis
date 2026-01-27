"""
Genesis exceptions
------------------

Grouping of all errors that can occur in genesis.
"""


class GenesisError(Exception):
    """Base exception for all Genesis errors."""


class ConnectionError(GenesisError):
    """exception created to group all connection errors."""

    ...


class ChannelError(GenesisError):
    """Exception raised for channel-related errors."""

    ...


class ConnectionTimeoutError(ConnectionError):
    """Occurs when the connection does not occur within the established timeout."""

    ...


class SessionGoneAway(GenesisError):
    """Occurs when the session has already received a hangup."""

    ...


class AuthenticationError(GenesisError, ValueError):
    """It happens when we have a problem during authentication."""

    ...


class UnconnectedError(GenesisError):
    """It happens when we try to send dice to a server once we connect before."""

    ...


class OperationInterruptedException(Exception):
    """Occurs when an operation (e.g., playback) is interrupted by a hangup or other event."""

    def __init__(
        self,
        message: str,
        event_uuid: str | None = None,
        channel_uuid: str | None = None,
    ) -> None:
        super().__init__(message)
        self.event_uuid = event_uuid
        self.channel_uuid = channel_uuid


class OriginateError(Exception):
    """Raised when a channel origination attempt fails."""

    def __init__(
        self,
        message: str,
        destination: str,
        variables: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.destination = destination
        self.variables = variables or {}


class TimeoutError(GenesisError):
    """Occurs when an operation times out (e.g., waiting for an event)."""

    ...
