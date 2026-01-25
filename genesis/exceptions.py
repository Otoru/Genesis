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


class AuthenticationError(GenesisError):
    """It happens when we have a problem during authentication."""

    ...


class UnconnectedError(GenesisError):
    """It happens when we try to send dice to a server once we connect before."""

    ...


class TimeoutError(GenesisError):
    """Occurs when an operation times out (e.g., waiting for an event)."""

    ...
