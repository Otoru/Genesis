import importlib.metadata

# Core protocol components (original API - preserved for backward compatibility)
from .consumer import Consumer, filtrate
from .outbound import Outbound, Session, ESLEvent
from .inbound import Inbound

# New shared modules (Phase 1)
from .enums import ChannelState, CallState
from .utils import build_variable_string
from .exceptions import (
    ConnectionError,
    ConnectionTimeoutError,
    SessionGoneAway,
    AuthenticationError,
    UnconnectedError,
    OperationInterruptedException,
    OriginateError,
)

# channels submodule available as genesis.channels
from . import channels

__all__ = [
    # Core (original)
    "Inbound",
    "Consumer",
    "filtrate",
    "Outbound",
    "Session",
    "ESLEvent",
    # Enums
    "ChannelState",
    "CallState",
    # Utils
    "build_variable_string",
    # Exceptions
    "ConnectionError",
    "ConnectionTimeoutError",
    "SessionGoneAway",
    "AuthenticationError",
    "UnconnectedError",
    "OperationInterruptedException",
    "OriginateError",
    # Submodule
    "channels",
]
__version__ = importlib.metadata.version("genesis")
