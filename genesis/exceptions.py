"""
Genesis exceptions
------------------

Grouping of all errors that can occur in genesis.
"""

from typing import Dict


class ConnectionError(ConnectionError):
    """exception created to group all connection errors."""

    ...


class ConnectionTimeoutError(ConnectionError):
    """Occurs when the connection does not occur within the established timeout."""

    ...


class SessionGoneAway(Exception):
    """Occurs when the session has already received a hangup."""

    ...


class AuthenticationError(ValueError):
    """It happens when we have a problem during authentication."""

    ...


class UnconnectedError(Exception):
    """It happens when we try to send dice to a server once we connect before."""


class OperationInterruptedException(Exception):
    """Occurs when an operation (e.g., playback) is interrupted by a hangup or other event."""

    def __init__(self, message: str, event_uuid: str | None = None, channel_uuid: str | None = None):
        super().__init__(message)
        self.event_uuid = event_uuid
        self.channel_uuid = channel_uuid


class OriginateError(Exception):
    """Raised when a channel origination attempt fails."""

    def __init__(self, message: str, destination: str, variables: Dict[str, str] = None):
        super().__init__(message)
        self.destination = destination
        self.variables = variables or {}
