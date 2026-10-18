"""Byte-level ESL codec.

This module does not import genesis. Framing follows FreeSWITCH 1.11.3
``mod_event_socket.c`` (git ``ef32e205295e29f034f1453ad245ba5efb07b94a``):

- Header lines end with ``\\n``. A blank line ends the header block and is
  not part of the body.
- ``Content-Length`` is ``strlen`` of the body: UTF-8 bytes, not characters.
- Inbound reads also accept ``\\r`` as a line ending.
- Outbound writes use ``\\n`` only. ``encode_frame`` does the same.
- Inbound commands are stored on a ``SWITCH_EVENT_CLONE``, which does not
  set ``EF_UNIQ_HEADERS``, so repeated header names stay as separate lines.
- A length above ``MAX_CONTENT_LENGTH`` (16 MiB) is rejected.
"""

from typing import List, Optional, Sequence, Tuple

MAX_CONTENT_LENGTH = 16 * 1024 * 1024

Header = Tuple[str, str]


class ESLCodecError(Exception):
    """A frame cannot be encoded or decoded."""


class IncompleteFrame(ESLCodecError):
    """The stream ended before a header block or body was complete."""


class ContentLengthError(ESLCodecError):
    """``Content-Length`` is invalid or disagrees with the body."""


class ESLFrame:
    """One ESL frame. Header order and duplicates are preserved."""

    def __init__(self, headers: Sequence[Header], body: bytes) -> None:
        self.headers: Tuple[Header, ...] = tuple(headers)
        self.body: bytes = body

    def header_values(self, name: str) -> Tuple[str, ...]:
        folded = name.lower()
        return tuple(value for key, value in self.headers if key.lower() == folded)

    def header(self, name: str) -> Optional[str]:
        values = self.header_values(name)
        if not values:
            return None
        return values[0]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ESLFrame):
            return NotImplemented
        return self.headers == other.headers and self.body == other.body

    def __repr__(self) -> str:
        return "ESLFrame(headers=%r, body=%r)" % (self.headers, self.body)


def encode_frame(headers: Sequence[Header], body: bytes = b"") -> bytes:
    """Encode one frame. ``Content-Length`` must match ``len(body)``."""
    encoded_headers: List[Header] = []
    declared: List[int] = []
    saw_length = False
    for name, value in headers:
        _reject_broken_header(name, value)
        encoded_headers.append((name, value))
        if name.lower() == "content-length":
            saw_length = True
            declared.append(_parse_length(value))
    if declared and any(length != declared[0] for length in declared):
        raise ContentLengthError("Content-Length headers disagree")
    body_length = len(body)
    if declared and declared[0] != body_length:
        raise ContentLengthError(
            "Content-Length %s disagrees with %s body bytes"
            % (declared[0], body_length)
        )
    if body_length and not saw_length:
        encoded_headers.append(("Content-Length", str(body_length)))
    if body_length > MAX_CONTENT_LENGTH:
        raise ContentLengthError("Content-Length exceeds %s" % MAX_CONTENT_LENGTH)

    chunks: List[bytes] = []
    for name, value in encoded_headers:
        chunks.append(("%s: %s\n" % (name, value)).encode("utf-8"))
    chunks.append(b"\n")
    chunks.append(body)
    return b"".join(chunks)


def decode_frames(data: bytes) -> Tuple[ESLFrame, ...]:
    """Decode a complete buffer. Leftover bytes raise ``IncompleteFrame``."""
    decoder = ESLDecoder()
    frames = list(decoder.feed(data))
    frames.extend(decoder.finish())
    return tuple(frames)


class ESLDecoder:
    """Incremental decoder for fragmented and coalesced reads."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._pending_headers: Optional[Tuple[Header, ...]] = None
        self._pending_length = 0

    def feed(self, data: bytes) -> Tuple[ESLFrame, ...]:
        if data:
            self._buffer.extend(data)
        return tuple(self._drain())

    def finish(self) -> Tuple[ESLFrame, ...]:
        frames = self._drain()
        if self._buffer or self._pending_headers is not None:
            raise IncompleteFrame("stream ended before the frame was complete")
        return tuple(frames)

    def _drain(self) -> List[ESLFrame]:
        frames: List[ESLFrame] = []
        while True:
            if self._pending_headers is not None:
                if len(self._buffer) < self._pending_length:
                    return frames
                body = bytes(self._buffer[: self._pending_length])
                del self._buffer[: self._pending_length]
                frames.append(ESLFrame(self._pending_headers, body))
                self._pending_headers = None
                self._pending_length = 0
                continue

            _skip_leading_breaks(self._buffer)
            if not self._buffer:
                return frames
            split = _split_header_block(self._buffer)
            if split is None:
                return frames
            block, consumed = split
            headers = _parse_header_block(block)
            length = _agreed_length(headers)
            del self._buffer[:consumed]
            if length == 0:
                frames.append(ESLFrame(headers, b""))
                continue
            self._pending_headers = headers
            self._pending_length = length


def _reject_broken_header(name: str, value: str) -> None:
    if name == "" or ":" in name or "\n" in name or "\r" in name:
        raise ESLCodecError("invalid header name: %r" % (name,))
    if "\n" in value or "\r" in value:
        raise ESLCodecError("header value contains a line break: %r" % (name,))


def _parse_length(value: str) -> int:
    if not value.isdigit():
        raise ContentLengthError("invalid Content-Length: %r" % (value,))
    length = int(value)
    if length > MAX_CONTENT_LENGTH:
        raise ContentLengthError("Content-Length exceeds %s" % MAX_CONTENT_LENGTH)
    return length


def _agreed_length(headers: Sequence[Header]) -> int:
    declared: List[int] = []
    for name, value in headers:
        if name.lower() == "content-length":
            declared.append(_parse_length(value))
    if not declared:
        return 0
    if any(length != declared[0] for length in declared):
        raise ContentLengthError("Content-Length headers disagree")
    return declared[0]


def _skip_leading_breaks(buffer: bytearray) -> None:
    index = 0
    while index < len(buffer) and buffer[index] in (10, 13):
        index += 1
    if index:
        del buffer[:index]


def _split_header_block(buffer: bytearray) -> Optional[Tuple[bytes, int]]:
    """Return header bytes and the index just after the blank line."""
    size = len(buffer)
    index = 0
    while index < size:
        if buffer[index] == 10:
            if index + 1 < size and buffer[index + 1] == 10:
                return bytes(buffer[:index]), index + 2
            if index + 2 < size and buffer[index + 1] == 13 and buffer[index + 2] == 10:
                return bytes(buffer[:index]), index + 3
        index += 1
    return None


def _parse_header_block(block: bytes) -> Tuple[Header, ...]:
    try:
        text = block.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ESLCodecError("header block is not utf-8") from exc
    headers: List[Header] = []
    for line in text.split("\n"):
        if line.endswith("\r"):
            line = line[:-1]
        if line == "":
            continue
        name, separator, value = line.partition(":")
        if separator != ":" or name == "" or name != name.strip():
            raise ESLCodecError("malformed header line: %r" % (line,))
        headers.append((name, value.lstrip(" ")))
    if not headers:
        raise ESLCodecError("empty header block")
    return tuple(headers)
