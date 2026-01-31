"""
Genesis Channels Submodule
--------------------------

OOP abstractions for FreeSWITCH channel management.
"""

from genesis.channels.bgapi import BackgroundAPI
from genesis.channels.channel import Channel
from genesis.channels.results import (
    AwaitableResult,
    BackgroundJobResult,
    CommandResult,
)
from genesis.channels.session import Session

__all__ = [
    "AwaitableResult",
    "BackgroundAPI",
    "BackgroundJobResult",
    "Channel",
    "CommandResult",
    "Session",
]
