"""
Telemetry and logging helpers for Protocol.

This module centralizes OpenTelemetry tracing, metrics recording, and logging logic.
"""

import logging
from typing import Dict, Any

from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import tracer, events_received_counter
from genesis.observability import logger, TRACE_LEVEL_NUM


def build_event_attributes(event: ESLEvent) -> Dict[str, Any]:
    """Build OpenTelemetry attributes from an ESL event.

    Args:
        event: The ESL event to extract attributes from

    Returns:
        Dictionary of attributes suitable for OTel spans and metrics
    """
    attributes = {}

    for key, value in event.items():
        if key == "Event-Name":
            attr_name = "event.name"
        elif key == "Unique-ID":
            attr_name = "event.uuid"
        elif key == "Content-Type":
            attr_name = "event.content_type"
        else:
            slug = key.lower().replace("-", "_")
            attr_name = f"event.header.{slug}"

        if isinstance(value, (str, int, float, bool, list, tuple)):
            attributes[attr_name] = value

    # Routing / correlation attributes (explicit, low-cardinality keys) so the
    # ``process_event`` span carries routing info and the sniffer join key.
    _EXPLICIT = {
        "Call-Direction": "event.direction",
        "Channel-State": "event.channel_state",
        "Answer-State": "event.answer_state",
        "Hangup-Cause": "event.hangup_cause",
        "Event-Subclass": "event.subclass",
        "Channel-Call-UUID": "event.call_uuid",
        "Other-Leg-Unique-ID": "event.other_leg",
        "Caller-Context": "event.context",
        "Caller-Destination-Number": "event.destination_number",
    }
    for src, dst in _EXPLICIT.items():
        if src in event:
            value = event[src]
            if isinstance(value, list):
                value = value[0] if value else ""
            attributes[dst] = value

    # sip.call_id is the PRIMARY correlation key with the sniffer
    # (sniffer emits voip.call_id = SIP Call-ID). Join happens at the backend.
    sip_call_id = event.get("variable_sip_call_id")
    if sip_call_id:
        attributes["sip.call_id"] = (
            sip_call_id[0] if isinstance(sip_call_id, list) else sip_call_id
        )

    return attributes


def build_metric_attributes(event: ESLEvent) -> Dict[str, str]:
    """Build metric attributes from an ESL event.

    Args:
        event: The ESL event

    Returns:
        Dictionary of metric attributes
    """
    event_name = event.get("Event-Name", "UNKNOWN")
    content_type = event.get("Content-Type", "UNKNOWN")

    metric_attributes = {
        "event_name": event_name,
        "content_type": content_type,
    }

    # Add optional attributes
    if "Event-Subclass" in event:
        metric_attributes["event_subclass"] = event["Event-Subclass"]
    if "Call-Direction" in event:
        metric_attributes["direction"] = event["Call-Direction"]
    if "Channel-State" in event:
        metric_attributes["channel_state"] = event["Channel-State"]
    if "Answer-State" in event:
        metric_attributes["answer_state"] = event["Answer-State"]
    if "Hangup-Cause" in event:
        metric_attributes["hangup_cause"] = event["Hangup-Cause"]

    return metric_attributes


def record_event_metrics(event: ESLEvent) -> None:
    """Record event metrics.

    Args:
        event: The ESL event to record metrics for
    """
    try:
        metric_attributes = build_metric_attributes(event)
        events_received_counter.add(1, attributes=metric_attributes)
    except Exception:
        pass


def _log_channel_event(event: ESLEvent, name: str, uuid: str) -> None:
    logger.debug(f"Received an event: '{name}' for call '{uuid}'. ")
    if name == "CHANNEL_EXECUTE_COMPLETE":
        application = event.get("Application")
        response = event.get("Application-Response")
        logger.debug(f"Application: '{application}' - Response: '{response}'.")


def _log_command_reply(event: ESLEvent) -> None:
    if "Content-Type" not in event:
        return
    if event["Content-Type"] not in ["command/reply", "auth/request"]:
        return
    reply = event.get("Reply-Text", None)
    if reply and event["Content-Type"] == "command/reply":
        logger.debug(f"Received an command reply: '{reply}'.")
    if reply and event["Content-Type"] == "auth/request":
        logger.debug(f"Received an authentication reply: '{event}'.")


def _log_event_debug(event: ESLEvent) -> None:
    name = event.get("Event-Name", None)
    uuid = event.get("Unique-ID", None)
    if uuid and name:
        _log_channel_event(event, name, uuid)
    elif name:
        logger.debug(f"Received an event: '{name}'.")
    else:
        _log_command_reply(event)


def log_event(event: ESLEvent) -> None:
    """Log an ESL event with appropriate detail level.

    Args:
        event: The ESL event to log
    """
    try:
        if logger.isEnabledFor(TRACE_LEVEL_NUM):
            logger.trace(f"Received an event: '{event}'.")
            return
        if logger.isEnabledFor(logging.DEBUG):
            _log_event_debug(event)
    except Exception as e:
        logger.error(f"Error logging event: {str(e)} - Event: {event}")
