"""Log helpers and metric-attribute safety for protocol telemetry."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from genesis.protocol.metrics import safe_add
from genesis.protocol.parser import ESLEvent
from genesis.protocol.telemetry import (
    build_metric_attributes,
    log_event,
    record_event_metrics,
)

from tests.references.synthetic.telemetry_payloads import SIP_CALL_ID, UUID_A


def _event(**kwargs: str) -> ESLEvent:
    event = ESLEvent()
    for key, value in kwargs.items():
        event[key] = value
    return event


def _arm_debug(mock_logger: MagicMock) -> None:
    """DEBUG is on. TRACE stays off so log_event takes the debug path."""

    def enabled(level: int) -> bool:
        return level >= logging.DEBUG

    mock_logger.isEnabledFor.side_effect = enabled


def test_log_channel_event_regular() -> None:
    event = _event(**{"Unique-ID": "uuid-1", "Event-Name": "CHANNEL_STATE"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called()
    args = mock_logger.debug.call_args_list[0][0][0]
    assert "uuid-1" in args


def test_log_channel_event_execute_complete() -> None:
    event = _event(
        **{
            "Unique-ID": "uuid-2",
            "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
            "Application": "playback",
            "Application-Response": "200 OK",
        }
    )
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    assert mock_logger.debug.call_count == 2
    second_call = mock_logger.debug.call_args_list[1][0][0]
    assert "playback" in second_call
    assert "200 OK" in second_call


def test_log_command_reply_no_content_type() -> None:
    event = _event(**{"Reply-Text": "+OK"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_not_called()


def test_log_command_reply_command_reply() -> None:
    event = _event(**{"Content-Type": "command/reply", "Reply-Text": "+OK accepted"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called_once()
    assert "+OK accepted" in mock_logger.debug.call_args[0][0]


def test_log_command_reply_auth_request() -> None:
    event = _event(**{"Content-Type": "auth/request", "Reply-Text": "challenge"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called_once()


def test_log_command_reply_irrelevant_content_type() -> None:
    event = _event(**{"Content-Type": "text/event-plain", "Reply-Text": "something"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_not_called()


def test_log_event_debug_with_uuid() -> None:
    event = _event(**{"Event-Name": "CHANNEL_HANGUP", "Unique-ID": "uuid-3"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called()
    args = mock_logger.debug.call_args_list[0][0][0]
    assert "uuid-3" in args


def test_log_event_debug_without_uuid_with_name() -> None:
    event = _event(**{"Event-Name": "HEARTBEAT"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called_once()
    assert "HEARTBEAT" in mock_logger.debug.call_args[0][0]


def test_log_event_debug_command_reply_path() -> None:
    event = _event(**{"Content-Type": "command/reply", "Reply-Text": "+OK hello"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _arm_debug(mock_logger)
        log_event(event)
    mock_logger.debug.assert_called_once()
    assert "+OK hello" in mock_logger.debug.call_args[0][0]


def test_build_metric_attributes_omits_uuids() -> None:
    event = _event(
        **{
            "Event-Name": "CHANNEL_BRIDGE",
            "Content-Type": "text/event-plain",
            "Unique-ID": UUID_A,
            "variable_sip_call_id": SIP_CALL_ID,
            "Call-Direction": "inbound",
        }
    )
    attributes = build_metric_attributes(event)
    blob = " ".join(list(attributes) + list(attributes.values()))
    assert UUID_A not in blob
    assert SIP_CALL_ID not in blob
    assert "uuid" not in " ".join(attributes)
    assert attributes["event_name"] == "CHANNEL_BRIDGE"
    assert attributes["direction"] == "inbound"


def test_record_event_metrics_and_safe_add_swallow_provider_errors() -> None:
    event = _event(
        **{
            "Event-Name": "HEARTBEAT",
            "Content-Type": "text/event-plain",
            "Unique-ID": UUID_A,
        }
    )

    class _Broken:
        def add(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("missing provider")

    with patch(
        "genesis.protocol.telemetry.events_received_counter.add",
        side_effect=RuntimeError("missing provider"),
    ):
        record_event_metrics(event)

    safe_add(_Broken(), 1, attributes={"channel.uuid": UUID_A})
