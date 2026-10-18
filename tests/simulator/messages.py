"""ESL reply and event bytes for the simulator.

Encoding follows FreeSWITCH 1.11.3 ``switch_url_encode`` and
``mod_event_socket.c``. This module does not import genesis.
"""

from typing import List, Optional, Sequence, Tuple

from tests.simulator.codec import ESLFrame, Header, encode_frame

GOODBYE = b"Disconnected, goodbye.\nSee you at ClueCon! http://www.cluecon.com/\n"
RUDE_BODY = b"Access Denied, go away.\n"

_UNSAFE = set(b'\r\n #%&+:;<=>?@[\\]^`{|}"')
_HEX = b"0123456789ABCDEFabcdef"


def url_encode(value: str) -> str:
    """Percent-encode one header value the way ``switch_url_encode`` does."""
    if value == "":
        return "_undef_"
    raw = value.encode("utf-8")
    out: List[bytes] = []
    index = 0
    size = len(raw)
    while index < size:
        if (
            raw[index] == 37
            and index + 2 < size
            and raw[index + 1] in _HEX
            and raw[index + 2] in _HEX
        ):
            out.append(raw[index : index + 3])
            index += 3
            continue
        byte = raw[index]
        if byte < 0x20 or byte > 0x7E or byte in _UNSAFE:
            out.append(("%%%02X" % byte).encode("ascii"))
        else:
            out.append(bytes((byte,)))
        index += 1
    return b"".join(out).decode("ascii")


def command_reply(*headers: Header) -> bytes:
    """A bodyless ``command/reply``. ``headers`` follow ``Content-Type``."""
    block: List[Header] = [("Content-Type", "command/reply")]
    block.extend(headers)
    return encode_frame(block)


def reply_text(text: str) -> bytes:
    return command_reply(("Reply-Text", text))


def api_response(body: bytes) -> bytes:
    return encode_frame(
        (
            ("Content-Type", "api/response"),
            ("Content-Length", str(len(body))),
        ),
        body,
    )


def disconnect_notice(session_uuid: Optional[str] = None) -> bytes:
    headers: List[Header] = [("Content-Type", "text/disconnect-notice")]
    if session_uuid:
        headers.append(("Controlled-Session-UUID", session_uuid))
        headers.append(("Content-Disposition", "disconnect"))
    headers.append(("Content-Length", str(len(GOODBYE))))
    return encode_frame(headers, GOODBYE)


def rude_rejection() -> bytes:
    notice = disconnect_notice()
    rude = encode_frame(
        (
            ("Content-Type", "text/rude-rejection"),
            ("Content-Length", str(len(RUDE_BODY))),
        ),
        RUDE_BODY,
    )
    return rude + notice


def auth_request() -> bytes:
    return encode_frame((("Content-Type", "auth/request"),))


def event_plain(headers: Sequence[Header], body: bytes = b"") -> ESLFrame:
    """One ``text/event-plain`` frame. Header values are percent-encoded.

    ``switch_event_serialize`` (``switch_event.c`` around 1610) writes each
    header as ``name: value\\n``. A non-empty ``event->body`` is then
    ``Content-Length: <strlen>\\n\\n<body>``. A missing or empty body is a
    single extra ``\\n`` after the header lines, so the buffer ends with a
    blank line. That newline is part of the outer ``Content-Length``.
    """
    lines: List[str] = []
    for name, value in headers:
        lines.append("%s: %s\n" % (name, url_encode(value)))
    if body:
        lines.append("Content-Length: %s\n\n" % len(body))
        payload = ("".join(lines)).encode("utf-8") + body
    else:
        lines.append("\n")
        payload = ("".join(lines)).encode("utf-8")
    frame_headers: Tuple[Header, ...] = (
        ("Content-Length", str(len(payload))),
        ("Content-Type", "text/event-plain"),
    )
    return ESLFrame(frame_headers, payload)


def encode_event(frame: ESLFrame) -> bytes:
    return encode_frame(frame.headers, frame.body)


def connect_reply(headers: Sequence[Header]) -> bytes:
    """Outbound ``connect`` body: a serialized event, no outer length."""
    lines: List[str] = []
    for name, value in headers:
        lines.append("%s: %s\n" % (name, url_encode(value)))
    lines.append("\n")
    return ("".join(lines)).encode("utf-8")
