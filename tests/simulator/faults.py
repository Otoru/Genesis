"""Opt-in faults. Synthetic bytes live under tests/references/synthetic."""

from enum import Enum
from pathlib import Path
from typing import Optional


class Fault(str, Enum):
    """Faults a scenario can arm. None of these are on by default."""

    BAD_PASSWORD = "bad_password"
    SHORT_BODY = "short_body"
    BAD_CONTENT_LENGTH = "bad_content_length"
    DROP_CONNECTION = "drop_connection"
    STALL_READS = "stall_reads"
    RUDE_REJECTION = "rude_rejection"
    DISCONNECT_BEFORE_REPLY = "disconnect_before_reply"
    ACK_THEN_DISCONNECT = "ack_then_disconnect"
    TRUNCATED_REPLY = "truncated_reply"
    CLEAN_EOF = "clean_eof"


_SYNTHETIC = Path(__file__).resolve().parents[1] / "references" / "synthetic"


def synthetic_payload(name: str) -> bytes:
    path = _SYNTHETIC / ("%s.raw" % name)
    return path.read_bytes()


def synthetic_meta(name: str) -> Optional[Path]:
    path = _SYNTHETIC / ("%s.meta.json" % name)
    if not path.is_file():
        return None
    return path
