"""
Genesis exceptions
------------------

Grouping of all errors that can occur in genesis.
"""

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

    ...
