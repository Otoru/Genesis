"""Tests for ESL reader state machine."""

import pytest

from genesis.protocol.reader_fsm import ESLReaderFSM, ReaderState
from tests.references.synthetic.legacy_payloads import channel_state, generic, heartbeat


def test_fsm_initial_state() -> None:
    """FSM starts in READING_HEADERS."""
    fsm = ESLReaderFSM()
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_headers_without_content_length() -> None:
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


def test_process_headers_with_content_length_zero() -> None:
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


def test_process_headers_with_content_length() -> None:
    """Headers with Content-Length > 0 transition to READING_BODY and return length."""
    fsm = ESLReaderFSM()
    block = "Content-Type: text/event-plain\nContent-Length: 10\n\n"
    events, content_length = fsm.process_headers(block)
    assert content_length == 10
    assert len(events) == 0
    assert fsm.state == ReaderState.READING_BODY


def test_process_body_simple() -> None:
    """Reading body produces one event and resets to READING_HEADERS."""
    fsm = ESLReaderFSM()
    block = "Content-Type: api/response\nContent-Length: 5\n\n"
    fsm.process_headers(block)
    body_events = fsm.process_body(b"hello")
    assert len(body_events) == 1
    assert body_events[0].body == "hello"
    assert fsm.state == ReaderState.READING_HEADERS


def test_process_body_event_plain() -> None:
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


def test_process_headers_twice_after_body() -> None:
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


def test_process_body_without_pending_raises() -> None:
    """process_body without prior process_headers that returned length raises."""
    fsm = ESLReaderFSM()
    with pytest.raises(RuntimeError, match="without pending event"):
        fsm.process_body(b"x")


def test_process_body_event_lock_multiple_events() -> None:
    """Synthetic parser compatibility input, not FreeSWITCH behavior.

    FreeSWITCH does not merge event-lock events into one frame. This body
    only covers how the reader splits such input.
    """
    fsm = ESLReaderFSM()
    body_content = (
        "Event-Name: CHANNEL_STATE\n"
        "Unique-ID: abc-123\n"
        "Event-Lock: true\n"
        "Event-Name: CHANNEL_ANSWER\n"
        "Unique-ID: abc-123\n"
        "\n"
        "some body"
    )
    body_bytes = body_content.encode("utf-8")
    block = f"Content-Type: text/event-plain\nContent-Length: {len(body_bytes)}\n\n"
    fsm.process_headers(block)
    events = fsm.process_body(body_bytes)
    assert len(events) >= 2


def test_process_body_event_lock_single_part() -> None:
    """Synthetic parser compatibility input, not FreeSWITCH behavior.

    One ``Event-Name`` in an event-lock body yields one event. That shape was
    not observed on FreeSWITCH 1.11.3.
    """
    fsm = ESLReaderFSM()
    body_content = "Event-Name: CHANNEL_STATE\nEvent-Lock: true\n\n"
    body_bytes = body_content.encode("utf-8")
    block = f"Content-Type: text/event-plain\nContent-Length: {len(body_bytes)}\n\n"
    fsm.process_headers(block)
    events = fsm.process_body(body_bytes)
    assert len(events) == 1
    assert events[0].get("Event-Name") == "CHANNEL_STATE"


def test_assemble_events_multiple_parts_inherit_headers() -> None:
    """Synthetic parser compatibility input, not FreeSWITCH behavior.

    Extra parts of an event-lock body inherit ``Content-Type``. FreeSWITCH
    emits separate frames and does not put event-lock in the body.
    """
    fsm = ESLReaderFSM()
    body_content = (
        "Event-Name: CHANNEL_STATE\n"
        "Unique-ID: id-1\n"
        "Event-Lock: true\n"
        "Event-Name: CHANNEL_EXECUTE\n"
        "Unique-ID: id-1\n"
        "\n"
    )
    body_bytes = body_content.encode("utf-8")
    block = f"Content-Type: text/event-plain\nContent-Length: {len(body_bytes)}\n\n"
    fsm.process_headers(block)
    events = fsm.process_body(body_bytes)
    assert len(events) >= 2
    for event in events[1:]:
        assert event.get("Content-Type") == "text/event-plain"
