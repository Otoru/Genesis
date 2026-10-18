import re
from pathlib import Path

import pytest

from tests.simulator.codec import (
    MAX_CONTENT_LENGTH,
    ContentLengthError,
    ESLCodecError,
    ESLDecoder,
    ESLFrame,
    Header,
    IncompleteFrame,
    decode_frames,
    encode_frame,
)
from tests.simulator.messages import encode_event, event_plain

REFERENCES = Path(__file__).resolve().parents[1] / "references" / "real" / "1.11.3"

AUTH_REQUEST = b"Content-Type: auth/request\n\n"
AUTH_OK = b"Content-Type: command/reply\nReply-Text: +OK accepted\n\n"
BAD_AUTH = (
    b"Content-Type: auth/request\n\n"
    b"Content-Type: command/reply\nReply-Text: -ERR invalid\n\n"
    b"Content-Type: text/disconnect-notice\nContent-Length: 67\n\n"
    b"Disconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n"
)
UNICODE_BODY = bytes.fromhex("636166c3a92de7a094e7a9b6")
UNICODE_FRAME = b"Content-Type: api/response\nContent-Length: 12\n\n" + UNICODE_BODY
ENCODED_PREFIX = (
    b"Content-Type: command/reply\n"
    b"Reply-Text: +OK ad489b9b-d025-4549-96ba-4fc5f57c158e\n\n"
    b"Content-Length: 605\nContent-Type: text/event-plain\n\n"
    b"Event-Subclass: esl.research.enc\n"
    b"Command: sendevent%20CUSTOM\n"
    b"research-note: caf%C3%A9%20test\n"
)


def test_auth_request_golden_bytes():
    encoded = encode_frame((("Content-Type", "auth/request"),))
    assert encoded == AUTH_REQUEST
    assert decode_frames(AUTH_REQUEST) == (
        ESLFrame((("Content-Type", "auth/request"),), b""),
    )


def test_auth_ok_golden_bytes():
    encoded = encode_frame(
        (("Content-Type", "command/reply"), ("Reply-Text", "+OK accepted"))
    )
    assert encoded == AUTH_OK
    frame = decode_frames(AUTH_OK)[0]
    assert frame.header("Reply-Text") == "+OK accepted"
    assert frame.body == b""


def test_unicode_body_uses_utf8_byte_length():
    assert UNICODE_BODY.decode("utf-8") == "café-研究"
    assert len("café-研究") == 7
    assert len(UNICODE_BODY) == 12
    assert (REFERENCES / "unicode_api_response.raw").read_bytes() == UNICODE_FRAME
    encoded = encode_frame(
        (("Content-Type", "api/response"), ("Content-Length", "12")),
        UNICODE_BODY,
    )
    assert encoded == UNICODE_FRAME
    frame = decode_frames(UNICODE_FRAME)[0]
    assert frame.header("Content-Length") == "12"
    assert frame.body == UNICODE_BODY
    assert len(frame.body) == 12


def test_bad_auth_capture_round_trip():
    captured = (REFERENCES / "bad_auth.raw").read_bytes()
    assert captured == BAD_AUTH
    frames = decode_frames(captured)
    assert len(frames) == 3
    assert frames[0].headers == (("Content-Type", "auth/request"),)
    assert frames[1].header("Reply-Text") == "-ERR invalid"
    assert frames[2].header("Content-Type") == "text/disconnect-notice"
    assert frames[2].header("Content-Length") == "67"
    assert frames[2].body == (
        b"Disconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n"
    )
    assert len(frames[2].body) == 67
    assert (
        b"".join(encode_frame(frame.headers, frame.body) for frame in frames)
        == captured
    )


def test_header_encoding_capture_has_no_body():
    captured = (REFERENCES / "header_encoding.raw").read_bytes()
    assert captured == (
        b"Content-Type: command/reply\n"
        b"Reply-Text: +OK c668ed3b-9cf9-4270-81c4-571bbf2c6899\n\n"
    )
    frame = decode_frames(captured)[0]
    assert frame.body == b""
    assert encode_frame(frame.headers, frame.body) == captured


def _captured_event_headers(body: bytes) -> tuple[Header, ...]:
    """Headers of one serialized event that has no inner body."""
    text = body.decode("utf-8")
    if not text.endswith("\n\n"):
        raise AssertionError("captured no-body event does not end with a blank line")
    headers = []
    for line in text[:-2].split("\n"):
        name, separator, value = line.partition(": ")
        if separator != ": " or name == "":
            raise AssertionError("captured event line is not a header: %r" % (line,))
        headers.append((name, value))
    return tuple(headers)


def test_event_plain_no_body_matches_captured_bytes():
    """Inner layout of a real CUSTOM event with no event body.

    ``filter_isolation_a.raw`` is the sendevent delivered to connection A.
    The outer ``Content-Length`` is 595 and the inner buffer has no
    ``Content-Length`` of its own. ``switch_event.c`` still appends one
    newline after the header lines. The comparison is the whole inner
    buffer, not a substring of a frame this test encoded first.
    """
    captured = (REFERENCES / "filter_isolation_a.raw").read_bytes()
    frames = decode_frames(captured)
    assert len(frames) == 2
    event = frames[1]
    assert event.header("Content-Type") == "text/event-plain"
    assert event.header("Content-Length") == "595"
    assert len(event.body) == 595
    assert b"Content-Length:" not in event.body
    headers: tuple = _captured_event_headers(event.body)
    assert headers[0] == ("Event-Subclass", "esl.research.a")
    assert ("Event-Name", "CUSTOM") in headers
    rebuilt = event_plain(headers)
    assert rebuilt.body == event.body
    assert len(rebuilt.body) == len(event.body) == 595
    assert encode_event(rebuilt) == encode_frame(event.headers, event.body)


def test_encoded_event_keeps_inner_blank_line_and_percent_encoding():
    captured = (REFERENCES / "encoded_event.raw").read_bytes()
    assert captured.startswith(ENCODED_PREFIX)
    frames = decode_frames(captured)
    assert len(frames) == 2
    assert frames[0].header("Content-Type") == "command/reply"
    assert frames[0].body == b""
    body = frames[1].body
    assert frames[1].header("Content-Length") == "605"
    assert len(body) == 605
    assert b"research-note: caf%C3%A9%20test\n" in body
    assert b"\n\n" in body
    assert (
        b"".join(encode_frame(frame.headers, frame.body) for frame in frames)
        == captured
    )


def test_fragmented_auth_request_at_six_bytes():
    decoder = ESLDecoder()
    assert decoder.feed(AUTH_REQUEST[:6]) == ()
    assert decoder.feed(AUTH_REQUEST[6:]) == (
        ESLFrame((("Content-Type", "auth/request"),), b""),
    )
    assert decoder.finish() == ()


def test_body_arrives_in_fragments():
    decoder = ESLDecoder()
    head = b"Content-Type: api/response\nContent-Length: 5\n\n"
    assert decoder.feed(head + b"al") == ()
    assert decoder.feed(b"pha") == (
        ESLFrame(
            (("Content-Type", "api/response"), ("Content-Length", "5")),
            b"alpha",
        ),
    )


def test_coalesced_api_frames_decode_together():
    alpha = encode_frame((("Content-Type", "api/response"),), b"alpha")
    beta = encode_frame((("Content-Type", "api/response"),), b"beta")
    assert alpha == b"Content-Type: api/response\nContent-Length: 5\n\nalpha"
    assert beta == b"Content-Type: api/response\nContent-Length: 4\n\nbeta"
    frames = decode_frames(alpha + beta)
    assert [frame.body for frame in frames] == [b"alpha", b"beta"]


def test_incomplete_body_is_an_error_at_end_of_stream():
    decoder = ESLDecoder()
    assert decoder.feed(b"Content-Type: api/response\nContent-Length: 5\n\nalp") == ()
    with pytest.raises(IncompleteFrame):
        decoder.finish()


def test_incomplete_headers_are_an_error_at_end_of_stream():
    decoder = ESLDecoder()
    assert decoder.feed(b"Content-Type: auth/request\n") == ()
    with pytest.raises(IncompleteFrame):
        decoder.finish()


def test_content_length_must_match_body_on_encode():
    with pytest.raises(ContentLengthError):
        encode_frame((("Content-Length", "3"),), b"abcd")


def test_disagreeing_content_length_headers_are_rejected():
    raw = b"Content-Length: 1\nContent-Length: 2\nContent-Type: api/response\n\n"
    with pytest.raises(ContentLengthError):
        decode_frames(raw)


def test_non_integer_content_length_is_rejected():
    with pytest.raises(ContentLengthError):
        decode_frames(b"Content-Type: api/response\nContent-Length: no\n\n")


def test_content_length_above_freeswitch_max_is_rejected():
    too_big = str(MAX_CONTENT_LENGTH + 1)
    raw = ("Content-Type: api/response\nContent-Length: %s\n\n" % too_big).encode(
        "ascii"
    )
    with pytest.raises(ContentLengthError):
        decode_frames(raw)


def test_duplicate_headers_are_preserved():
    headers = (
        ("Content-Type", "command/reply"),
        ("X-Research", "one"),
        ("X-Research", "two"),
    )
    encoded = encode_frame(headers)
    assert encoded == (
        b"Content-Type: command/reply\nX-Research: one\nX-Research: two\n\n"
    )
    frame = decode_frames(encoded)[0]
    assert frame.headers == headers
    assert frame.header_values("X-Research") == ("one", "two")
    assert frame.header_values("x-research") == ("one", "two")


def test_crlf_header_block_decodes():
    raw = b"Content-Type: auth/request\r\n\r\n"
    frame = decode_frames(raw)[0]
    assert frame.headers == (("Content-Type", "auth/request"),)
    assert frame.body == b""


def test_malformed_header_line_is_rejected():
    with pytest.raises(ESLCodecError):
        decode_frames(b"not-a-header\n\n")


def test_simulator_package_does_not_import_genesis():
    root = Path(__file__).resolve().parents[1] / "simulator"
    for path in sorted(root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^\s*(import genesis\b|from genesis\b)", text) is None


def test_reference_sidecars_are_not_inside_the_wire_bytes():
    for raw_path in sorted(REFERENCES.glob("*.raw")):
        payload = raw_path.read_bytes()
        assert not payload.startswith(b"#")
        meta = raw_path.with_suffix(".meta.json").read_text(encoding="utf-8")
        assert '"kind": "real"' in meta
        assert "1.11.3" in meta
