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


def log_event(event: ESLEvent) -> None:
    """Log an ESL event with appropriate detail level.

    Args:
        event: The ESL event to log
    """
    try:
        if logger.isEnabledFor(TRACE_LEVEL_NUM):
            logger.trace(f"Received an event: '{event}'.")
            return

        if not logger.isEnabledFor(logging.DEBUG):
            return

        name = event.get("Event-Name", None)
        uuid = event.get("Unique-ID", None)

        if uuid:
            logger.debug(f"Received an event: '{name}' for call '{uuid}'. ")

            if name == "CHANNEL_EXECUTE_COMPLETE":
                application = event.get("Application")
                response = event.get("Application-Response")
                logger.debug(f"Application: '{application}' - Response: '{response}'.")
        else:
            if name:
                logger.debug(f"Received an event: '{name}'.")
            elif "Content-Type" in event and event["Content-Type"] in [
                "command/reply",
                "auth/request",
            ]:
                reply = event.get("Reply-Text", None)

                if reply and event["Content-Type"] == "command/reply":
                    logger.debug(f"Received an command reply: '{reply}'.")

                if reply and event["Content-Type"] == "auth/request":
                    logger.debug(f"Received an authentication reply: '{event}'.")

    except Exception as e:
        logger.error(f"Error logging event: {str(e)} - Event: {event}")
