"""
ESL Reader State Machine
-------------------------

State machine for reading and parsing ESL messages from a stream.
States: READING_HEADERS -> (optional) READING_BODY -> emit event(s) -> READING_HEADERS.
"""

from enum import Enum, auto
from typing import Optional, List, Tuple

from genesis.observability import logger
from genesis.protocol.parser import ESLEvent, parse_headers


class ReaderState(Enum):
    """States of the ESL reader FSM."""

    READING_HEADERS = auto()
    READING_BODY = auto()


class ESLReaderFSM:
    """
    State machine that parses ESL protocol messages.

    Consumes header blocks and optional body chunks, produces complete
    ESLEvent instances. Call process_headers() when a full header block
    is received; if it returns a content_length, call process_body()
    with that many bytes.
    """

    __slots__ = ("_state", "_pending_event", "_content_length", "_content_type")

    def __init__(self) -> None:
        self._state = ReaderState.READING_HEADERS
        self._pending_event: Optional[ESLEvent] = None
        self._content_length: int = 0
        self._content_type: Optional[str] = None

    @property
    def state(self) -> ReaderState:
        return self._state

    @property
    def content_length(self) -> int:
        """Bytes to read for body when state is READING_BODY."""
        return self._content_length

    def process_headers(self, header_block: str) -> Tuple[List[ESLEvent], int]:
        """
        Process a complete header block (ends with \\n\\n or \\r\\n\\r\\n).

        Returns:
            - List of events to emit immediately (empty if body must be read first).
            - Content length to read (0 if no body). Call process_body() after reading.
        """
        if self._state != ReaderState.READING_HEADERS:
            raise RuntimeError(
                f"process_headers called in state {self._state.name}; "
                "expected READING_HEADERS"
            )

        event = parse_headers(header_block)
        events: List[ESLEvent] = []

        if "Content-Length" not in event:
            event.body = None
            return ([event], 0)

        length = int(event["Content-Length"].split("\n")[0])
        if length == 0:
            # Empty body: emit event immediately, do not transition to READING_BODY
            event.body = None
            return ([event], 0)

        self._pending_event = event
        self._content_length = length
        self._content_type = event.get("Content-Type")
        self._state = ReaderState.READING_BODY
        return (events, length)

    def process_body(self, raw_body: bytes) -> List[ESLEvent]:
        """
        Process body bytes after process_headers returned a content_length > 0.

        Returns list of events (1 or more when event-lock produces multiple).
        """
        if self._state != ReaderState.READING_BODY or self._pending_event is None:
            raise RuntimeError(
                "process_body called without pending event; "
                "call process_headers and read content_length bytes first"
            )

        complete_content = raw_body.decode("utf-8")
        logger.trace(f"Received complete data: {raw_body!r}")

        event = self._pending_event
        content_type = self._content_type

        if content_type and content_type not in [
            "api/response",
            "text/rude-rejection",
            "log/data",
        ]:
            if "\n\n" in complete_content:
                headers_part, body = complete_content.split("\n\n", 1)
                event_parts: List[str] = []

                if "event-lock: true" in headers_part.lower():
                    parts = headers_part.split("\nEvent-Name: ")
                    if len(parts) > 1:
                        event_parts = [parts[0]]
                        for part in parts[1:]:
                            event_parts.append(f"Event-Name: {part}")
                        logger.debug(
                            f"Split locked event into {len(event_parts)} separate events"
                        )
                else:
                    event_parts = [headers_part]

                events_out: List[ESLEvent] = []
                body_value: Optional[str] = body if body else None
                for idx, event_str in enumerate(event_parts):
                    if idx == 0:
                        additional = parse_headers(event_str)
                        event.update(additional)
                        event.body = body_value
                        events_out.append(event)
                    else:
                        new_event = parse_headers(event_str)
                        for key in ["Content-Length", "Content-Type"]:
                            if key in event:
                                new_event[key] = event[key]
                        new_event.body = body_value
                        events_out.append(new_event)
                self._reset_to_headers()
                return events_out
            else:
                if content_type == "text/event-plain":
                    additional = parse_headers(complete_content)
                    event.update(additional)
                    event.body = None
                else:
                    event.body = complete_content if complete_content else None
        else:
            event.body = complete_content if complete_content else None

        self._reset_to_headers()
        return [event]

    def _reset_to_headers(self) -> None:
        self._state = ReaderState.READING_HEADERS
        self._pending_event = None
        self._content_length = 0
        self._content_type = None
