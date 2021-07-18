"""
Genesis exceptions
------------------

Grouping of all errors that can occur in genesis.
"""


class ConnectionTimeoutError(Exception):
    """Occurs when the connection does not occur within the established timeout."""

    ...


class AuthenticationError(ValueError):
    """It happens when we have a problem during authentication."""

    ...


class UnconnectedError(Exception):
    """It happens when we try to send dice to a server once we connect before."""

    ...
