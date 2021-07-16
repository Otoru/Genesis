"""
Genesis parse
-------------

It implements the intelligence necessary for us to transform freeswitch events into python primitive types.
"""
from urllib.parse import unquote
from typing import Dict


def parse(payload: str) -> Dict[str, str]:
    """Given the payload of an event, it returns a dictionary with its information."""
    unquoted_payload = unquote(payload, encoding="UTF-8")
    lines = unquoted_payload.strip().splitlines()
    result = {}
    buffer = ""
    value = ""

    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            buffer = key
        else:
            key = buffer
            value += "\n" + line

        result[key.strip()] = value.strip()

    return result
