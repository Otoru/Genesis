"""
Enumerations for FreeSWITCH States
----------------------------------

This module defines enumerations used to represent various states
within the FreeSWITCH system, particularly for channels.
"""

from enum import IntEnum, auto


class ChannelState(IntEnum):
    """
    Represents the core state of a FreeSWITCH channel.

    Corresponds to the CS_* definitions in FreeSWITCH.
    See: https://developer.signalwire.com/freeswitch/FreeSWITCH-Explained/Dialplan/Channel-States_7144639
    """
    NEW = 0
    INIT = 1
    ROUTING = 2
    SOFT_EXECUTE = 3
    EXECUTE = 4
    EXCHANGE_MEDIA = 5
    PARK = 6
    CONSUME_MEDIA = 7
    HIBERNATE = 8
    RESET = 9
    HANGUP = 10
    REPORTING = 11
    DESTROY = 12
    NONE = 13 # Should generally not be encountered in normal operation


class CallState(IntEnum):
    """
    Represents the call-specific state of a FreeSWITCH channel.

    Corresponds to the CCS_* definitions or common channel variable states.
    Note: FreeSWITCH itself doesn't have a single unified 'CallState' enum like ChannelState.
    This combines common states often tracked via variables or internal logic.
    """
    DOWN = 0 # Initial state or after hangup
    DIALING = auto()
    RINGING = auto()
    EARLY = auto() # Early media
    ACTIVE = auto() # Call is answered and active
    HELD = auto()
    RING_WAIT = auto() # Waiting for ring after dialing
    HANGUP = auto() # Hangup initiated/in progress (before CS_HANGUP/DESTROY)
    UNHELD = auto() # Transition state after unhold
