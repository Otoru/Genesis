"""
Genesis parse
-------------
It implements the intelligence necessary for us to transform freeswitch events into python primitive types.
"""

from typing import Dict, Type
from urllib.parse import unquote

from .events import (
    ESLEvent,
    HeartbeatEvent, CustomEvent, ChannelCreateEvent, ChannelAnswerEvent,
    ChannelHangupEvent, ChannelDestroyEvent, ChannelExecuteEvent,
    ChannelExecuteCompleteEvent, ChannelBridgeEvent, ChannelUnbridgeEvent,
    ConferenceDataEvent, ConferenceEventEvent, ConferenceRecordEvent,
    ModuleUnloadEvent, ChannelHangupCompleteEvent, BackgroundJobEvent, ApiEvent,
    MessageEvent, PresenceInEvent, NotifyEvent
)

# Map event names to specific classes
EVENT_CLASS_MAP: Dict[str, Type[ESLEvent]] = {
    "HEARTBEAT": HeartbeatEvent,
    "CUSTOM": CustomEvent,
    "CHANNEL_CREATE": ChannelCreateEvent,
    "CHANNEL_ANSWER": ChannelAnswerEvent,
    "CHANNEL_HANGUP": ChannelHangupEvent,
    "CHANNEL_DESTROY": ChannelDestroyEvent,
    "CHANNEL_EXECUTE": ChannelExecuteEvent,
    "CHANNEL_EXECUTE_COMPLETE": ChannelExecuteCompleteEvent,
    "CHANNEL_BRIDGE": ChannelBridgeEvent,
    "CHANNEL_UNBRIDGE": ChannelUnbridgeEvent,
    "CHANNEL_HANGUP_COMPLETE": ChannelHangupCompleteEvent,
    # Conference Events
    "CONFERENCE_DATA": ConferenceDataEvent,
    "CONFERENCE_EVENT": ConferenceEventEvent,
    "CONFERENCE_RECORD": ConferenceRecordEvent,
    # System/Maintenance/Debugging Events
    "MODULE_UNLOAD": ModuleUnloadEvent,
    "BACKGROUND_JOB": BackgroundJobEvent,
    "API": ApiEvent,
    # Specialized Communication Events
    "MESSAGE": MessageEvent,
    "PRESENCE_IN": PresenceInEvent,
    "NOTIFY": NotifyEvent,
}


def parse_headers(payload: str) -> ESLEvent:
    lines = payload.strip().splitlines()
    headers_dict = {}
    buffer = ""
    value = ""

    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            buffer = key
        else:
            value += "\n" + line
            key = buffer

        key = unquote(key.strip(), encoding="UTF-8")
        value = unquote(value.strip(), encoding="UTF-8")

        if ": " in line and key in headers_dict:
            backup = headers_dict[key]
            if isinstance(backup, str):
                headers_dict[key] = [backup, value]
            else:
                # Ensure backup is a list before extending
                if isinstance(backup, list):
                    headers_dict[key] = [*backup, value]
                else: # Should not happen with current logic, but safeguard
                    headers_dict[key] = [backup, value]
        else:
            headers_dict[key] = value

    # Determine the correct event class
    event_name = headers_dict.get("Event-Name")
    event_class = EVENT_CLASS_MAP.get(event_name, ESLEvent)
    event = event_class(headers_dict)

    return event
