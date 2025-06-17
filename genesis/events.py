"""
Specific FreeSWITCH Event Classes
---------------------------------

This module defines specific classes for various FreeSWITCH events,
inheriting from the base class.
"""
from typing import Optional
from collections import UserDict


class ESLEvent(UserDict):
    """
    Base class for all ESL events.

    Acts like a dictionary but also holds an optional body attribute.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body: Optional[str] = None


# --- Specific Event Classes ---

class HeartbeatEvent(ESLEvent):
    """Represents a HEARTBEAT event from FreeSWITCH."""
    pass


class CustomEvent(ESLEvent):
    """Represents a CUSTOM event from FreeSWITCH. Check 'Event-Subclass' for details."""
    pass


# Channel Events
class ChannelCreateEvent(ESLEvent):
    """Represents a CHANNEL_CREATE event."""
    pass


class ChannelAnswerEvent(ESLEvent):
    """Represents a CHANNEL_ANSWER event."""
    pass


class ChannelHangupEvent(ESLEvent):
    """Represents a CHANNEL_HANGUP event."""
    pass


class ChannelDestroyEvent(ESLEvent):
    """Represents a CHANNEL_DESTROY event."""
    pass


class ChannelExecuteEvent(ESLEvent):
    """Represents a CHANNEL_EXECUTE event."""
    pass


class ChannelExecuteCompleteEvent(ESLEvent):
    """Represents a CHANNEL_EXECUTE_COMPLETE event."""
    pass


class ChannelBridgeEvent(ESLEvent):
    """Represents a CHANNEL_BRIDGE event."""
    pass


class ChannelUnbridgeEvent(ESLEvent):
    """Represents a CHANNEL_UNBRIDGE event."""
    pass


# Conference Events
class ConferenceDataEvent(ESLEvent):
    """Represents a CONFERENCE_DATA event."""
    pass


class ConferenceEventEvent(ESLEvent):
    """
    Represents a CONFERENCE_EVENT event.
    The specific action (e.g., add-member, start-talking) is usually in the 'Action' header.
    """
    pass


class ConferenceRecordEvent(ESLEvent):
    """Represents a CONFERENCE_RECORD event."""
    pass

# Add other CHANNEL_* events mentioned in events.md if needed, following the pattern.
# For now, sticking to the ones explicitly listed or implied by CHANNEL_*.

# Add other CONFERENCE_* events mentioned in events.md if needed.


# System and Maintenance Events
class ModuleUnloadEvent(ESLEvent):
    """Represents a MODULE_UNLOAD event."""
    pass


# Error and Debugging Events
class ChannelHangupCompleteEvent(ESLEvent):
    """Represents a CHANNEL_HANGUP_COMPLETE event."""
    pass


class BackgroundJobEvent(ESLEvent):
    """Represents a BACKGROUND_JOB event."""
    pass


class ApiEvent(ESLEvent):
    """Represents an API event (logs API calls)."""
    pass


# Specialized Communication Events
class MessageEvent(ESLEvent):
    """Represents a MESSAGE event (chat/SMS/IM)."""
    pass


class PresenceInEvent(ESLEvent):
    """Represents a PRESENCE_IN event (status updates)."""
    pass


class NotifyEvent(ESLEvent):
    """Represents a NOTIFY event (e.g., MWI)."""
    pass
