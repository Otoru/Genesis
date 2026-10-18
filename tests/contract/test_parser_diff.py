"""Genesis parser versus the simulator codec on the same captured bytes.

The simulator does not import Genesis. This module imports both so a
disagreement is visible in CI.
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import unquote

from genesis.protocol.parser import ESLEvent, parse_headers
from tests.simulator.codec import Header, decode_frames

REFERENCES = Path(__file__).resolve().parents[1] / "references" / "real" / "1.11.3"
PIN = "ef32e205295e29f034f1453ad245ba5efb07b94a"


def _grouped(headers: Tuple[Header, ...]) -> List[Tuple[str, List[str]]]:
    grouped: Dict[str, List[str]] = {}
    order: List[str] = []
    for name, value in headers:
        key = unquote(name)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(unquote(value))
    return [(key, grouped[key]) for key in order]


def _assert_parsed(headers: Tuple[Header, ...], parsed: ESLEvent) -> None:
    expected = _grouped(headers)
    assert list(parsed) == [name for name, _ in expected]
    for name, values in expected:
        got = parsed[name]
        if len(values) == 1:
            assert got == values[0]
        else:
            assert got == values


def _inner_headers(body: bytes) -> Tuple[Header, ...]:
    text = body.decode("utf-8")
    if not text.endswith("\n\n"):
        raise AssertionError("captured event body does not end with a blank line")
    headers: List[Header] = []
    for line in text[:-2].split("\n"):
        name, separator, value = line.partition(": ")
        if separator != ": " or name == "":
            raise AssertionError("captured event line is not a header: %r" % (line,))
        headers.append((name, value))
    return tuple(headers)


def _check(stem: str) -> None:
    meta_path = REFERENCES / ("%s.meta.json" % stem)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["freeswitch_version"] == "1.11.3"
    assert meta["git"] == PIN
    frames = decode_frames((REFERENCES / ("%s.raw" % stem)).read_bytes())
    for frame in frames:
        block = "".join("%s: %s\n" % (name, value) for name, value in frame.headers)
        _assert_parsed(frame.headers, parse_headers(block))
        if frame.header("Content-Type") != "text/event-plain":
            continue
        assert frame.header("Content-Length") == str(len(frame.body))
        inner = _inner_headers(frame.body)
        _assert_parsed(inner, parse_headers(frame.body[:-2].decode("utf-8")))


def test_parser_matches_codec_on_encoded_capture() -> None:
    """Percent-encoded ``research-note`` survives both decoders."""
    _check("encoded_event")


def test_parser_matches_codec_on_no_body_capture() -> None:
    """The no-body CUSTOM capture is headers plus the final blank line."""
    _check("filter_isolation_a")
