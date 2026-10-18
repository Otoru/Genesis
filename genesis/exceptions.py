"""
Genesis exceptions
------------------

Grouping of all errors that can occur in genesis.
"""

from enum import Enum


class GenesisError(Exception):
    """Base exception for all Genesis errors."""


class CommandStage(str, Enum):
    """Observed progress of one ESL command on the wire."""

    NOT_SENT = "NOT_SENT"
    UNCONFIRMED = "UNCONFIRMED"
    ACCEPTED = "ACCEPTED"


class ConnectionError(GenesisError):
    """exception created to group all connection errors."""

    ...


class ConnectionLost(ConnectionError):
    """The peer dropped the ESL connection.

    ``stage`` is only evidence already observed. ``NOT_SENT`` means
    ``write()`` was not called. ``UNCONFIRMED`` means ``write()`` was
    called and this waiter got no reply. Callers that already saw the
    ack pass ``ACCEPTED`` themselves. A delivered ``-ERR`` is not this error.
    """

    def __init__(
        self, stage: CommandStage, detail: str = "ESL connection lost"
    ) -> None:
        super().__init__(detail)
        self.stage = stage


class ChannelError(GenesisError):
    """Exception raised for channel-related errors."""

    ...


class ChannelNotFound(ChannelError):
    """No live channel exists for ``uuid``."""

    def __init__(self, uuid: str) -> None:
        super().__init__(f"channel {uuid} not found")
        self.uuid = uuid


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


class QueueTimeoutError(TimeoutError):
    """Occurs when waiting for a queue slot exceeds the optional timeout."""

    ...
