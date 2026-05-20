import asyncio
import logging
import pytest
from unittest.mock import patch
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry import trace
from genesis import Inbound
from genesis.exceptions import AuthenticationError
from genesis.protocol.parser import ESLEvent
from genesis.protocol.telemetry import (
    _log_channel_event,
    _log_command_reply,
    _log_event_debug,
)


@pytest.fixture
def memory_exporter():
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider = trace.get_tracer_provider()

    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

    provider.add_span_processor(processor)
    yield exporter


@pytest.fixture
def host():
    return lambda: "127.0.0.1"


async def wait_for_span(
    exporter: InMemorySpanExporter,
    span_name: str,
    timeout: float = 1.0,
) -> None:
    """Wait for a span to appear in the exporter using event-based polling."""
    start_time = asyncio.get_event_loop().time()
    check_event = asyncio.Event()

    async def check_loop():
        while True:
            spans = exporter.get_finished_spans()
            if any(s.name == span_name for s in spans):
                check_event.set()
                return

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                check_event.set()
                return

            future = asyncio.Future()
            asyncio.get_event_loop().call_soon(future.set_result, None)
            await future

    check_task = asyncio.create_task(check_loop())
    try:
        await asyncio.wait_for(check_event.wait(), timeout=timeout)
    finally:
        check_task.cancel()
        try:
            await check_task
        except asyncio.CancelledError:
            raise

    spans = exporter.get_finished_spans()
    if not any(s.name == span_name for s in spans):
        raise TimeoutError(f"Span '{span_name}' not found within {timeout}s")


async def test_inbound_connection_spans(freeswitch, memory_exporter):
    """Verify that connecting to FreeSWITCH generates an 'inbound_connect' span."""
    async with freeswitch:
        async with Inbound(*freeswitch.address) as _client:
            pass  # connect only, span verified below

    await wait_for_span(memory_exporter, "inbound_connect", timeout=1.0)

    spans = memory_exporter.get_finished_spans()
    connect_spans = [s for s in spans if s.name == "inbound_connect"]
    assert len(connect_spans) == 1
    span = connect_spans[0]
    assert span.attributes["net.peer.name"] == "127.0.0.1"
    assert "net.peer.port" in span.attributes


async def test_send_command_span(freeswitch, memory_exporter):
    """Verify that sending a command generates a 'send_command' span."""
    async with freeswitch:
        freeswitch.oncommand("uptime", "6943047")
        async with Inbound(*freeswitch.address) as client:
            await client.send("uptime")

    await wait_for_span(memory_exporter, "send_command", timeout=1.0)

    spans = memory_exporter.get_finished_spans()
    send_spans = [s for s in spans if s.name == "send_command"]
    assert len(send_spans) >= 1

    uptime_span = next(
        (s for s in send_spans if s.attributes["command.name"] == "uptime"), None
    )
    assert uptime_span is not None
    if "command.reply" in uptime_span.attributes:
        assert uptime_span.attributes["command.reply"] == "6943047"


def _make_event(**kwargs) -> ESLEvent:
    event = ESLEvent()
    for k, v in kwargs.items():
        event[k] = v
    return event


def test_log_channel_event_regular():
    event = _make_event(**{"Unique-ID": "uuid-1", "Event-Name": "CHANNEL_STATE"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        _log_channel_event(event, "CHANNEL_STATE", "uuid-1")
    mock_logger.debug.assert_called()
    args = mock_logger.debug.call_args_list[0][0][0]
    assert "uuid-1" in args


def test_log_channel_event_execute_complete():
    event = _make_event(
        **{
            "Unique-ID": "uuid-2",
            "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
            "Application": "playback",
            "Application-Response": "200 OK",
        }
    )
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        _log_channel_event(event, "CHANNEL_EXECUTE_COMPLETE", "uuid-2")
    assert mock_logger.debug.call_count == 2
    second_call = mock_logger.debug.call_args_list[1][0][0]
    assert "playback" in second_call
    assert "200 OK" in second_call


def test_log_command_reply_no_content_type():
    event = _make_event(**{"Reply-Text": "+OK"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _log_command_reply(event)
    mock_logger.debug.assert_not_called()


def test_log_command_reply_command_reply():
    event = _make_event(
        **{"Content-Type": "command/reply", "Reply-Text": "+OK accepted"}
    )
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _log_command_reply(event)
    mock_logger.debug.assert_called_once()
    assert "+OK accepted" in mock_logger.debug.call_args[0][0]


def test_log_command_reply_auth_request():
    event = _make_event(**{"Content-Type": "auth/request", "Reply-Text": "challenge"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _log_command_reply(event)
    mock_logger.debug.assert_called_once()


def test_log_command_reply_irrelevant_content_type():
    event = _make_event(
        **{"Content-Type": "text/event-plain", "Reply-Text": "something"}
    )
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        _log_command_reply(event)
    mock_logger.debug.assert_not_called()


def test_log_event_debug_with_uuid():
    event = _make_event(**{"Event-Name": "CHANNEL_HANGUP", "Unique-ID": "uuid-3"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        _log_event_debug(event)
    mock_logger.debug.assert_called()
    args = mock_logger.debug.call_args_list[0][0][0]
    assert "uuid-3" in args


def test_log_event_debug_without_uuid_with_name():
    event = _make_event(**{"Event-Name": "HEARTBEAT"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        _log_event_debug(event)
    mock_logger.debug.assert_called_once()
    assert "HEARTBEAT" in mock_logger.debug.call_args[0][0]


def test_log_event_debug_command_reply_path():
    event = _make_event(**{"Content-Type": "command/reply", "Reply-Text": "+OK hello"})
    with patch("genesis.protocol.telemetry.logger") as mock_logger:
        mock_logger.isEnabledFor.return_value = True
        _log_event_debug(event)
    mock_logger.debug.assert_called_once()
    assert "+OK hello" in mock_logger.debug.call_args[0][0]
