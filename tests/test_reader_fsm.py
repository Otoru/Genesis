"""Tests for ESL reader state machine."""

import pytest

from genesis.protocol.reader_fsm import ESLReaderFSM, ReaderState
from genesis.protocol.parser import ESLEvent

from tests.payloads import channel_state, generic, heartbeat


def test_fsm_initial_state():
    """FSM starts in READING_HEADERS."""
    fsm = ESLReaderFSM()
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_headers_without_content_length():
    """Headers without Content-Length emit one event and no body to read."""
    fsm = ESLReaderFSM()
    block = generic.strip() + "\n\n"
    events, content_length = fsm.process_headers(block)
    assert content_length == 0
    assert len(events) == 1
    assert events[0]["Content-Type"] == "command/reply"
    assert events[0]["Reply-Text"] == "Reply generic command"
    assert events[0].body is None
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_headers_with_content_length_zero():
    """Headers with Content-Length: 0 emit event immediately (no body read)."""
    fsm = ESLReaderFSM()
    block = (
        channel_state.format(
            unique_id="abc-123",
            state="CS_ROUTING",
            variable_test_key="test_value",
        ).strip()
        + "\n\n"
    )
    events, content_length = fsm.process_headers(block)
    assert content_length == 0
    assert len(events) == 1
    assert events[0]["Event-Name"] == "CHANNEL_STATE"
    assert events[0].body is None
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_headers_with_content_length():
    """Headers with Content-Length > 0 transition to READING_BODY and return length."""
    fsm = ESLReaderFSM()
    block = "Content-Type: text/event-plain\nContent-Length: 10\n\n"
    events, content_length = fsm.process_headers(block)
    assert content_length == 10
    assert len(events) == 0
    assert fsm.state == ReaderState.READING_BODY


def test_process_body_simple():
    """Reading body produces one event and resets to READING_HEADERS."""
    fsm = ESLReaderFSM()
    block = "Content-Type: api/response\nContent-Length: 5\n\n"
    fsm.process_headers(block)
    body_events = fsm.process_body(b"hello")
    assert len(body_events) == 1
    assert body_events[0].body == "hello"
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_body_event_plain():
    """text/event-plain body is parsed for additional headers."""
    fsm = ESLReaderFSM()
    first_line = heartbeat.strip().split("\n")[0]
    body = (first_line + "\n\n").encode()
    block = f"Content-Type: text/event-plain\nContent-Length: {len(body)}\n\n"
    fsm.process_headers(block)
    body_events = fsm.process_body(body)
    assert len(body_events) == 1
    assert body_events[0].get("Event-Name") == "HEARTBEAT"
    assert body_events[0].body is None


def test_process_headers_twice_after_body():
    """After process_body, next process_headers works (full cycle)."""
    fsm = ESLReaderFSM()
    block1 = generic.strip() + "\n\n"
    events1, _ = fsm.process_headers(block1)
    assert len(events1) == 1
    assert events1[0]["Reply-Text"] == "Reply generic command"

    block2 = (
        channel_state.format(
            unique_id="xyz-456",
            state="CS_HANGUP",
            variable_test_key="test",
        ).strip()
        + "\n\n"
    )
    events2, _ = fsm.process_headers(block2)
    assert len(events2) == 1
    assert events2[0]["Event-Name"] == "CHANNEL_STATE"
    assert events2[0]["Unique-ID"] == "xyz-456"


def test_process_body_without_pending_raises():
    """process_body without prior process_headers that returned length raises."""
    fsm = ESLReaderFSM()
    with pytest.raises(RuntimeError, match="without pending event"):
        fsm.process_body(b"x")
