"""
Genesis parse
-------------

It implements the intelligence necessary for us to transform freeswitch events into python primitive types.
"""
from urllib.parse import unquote
from typing import Dict


def parse(payload: str) -> Dict[str, str]:
    """Given the payload of an event, it returns a dictionary with its information."""
    lines = payload.strip().splitlines()
    body = False
    result = {}
    buffer = ""
    value = ""

    for line in lines:
        if not line:
            body = True
            continue

        elif ": " in line:
            key, value = line.split(": ", 1)
            buffer = key
            body = False

        elif body:
            key = "X-Event-Content"

            if key in result:
                value += "\n" + line
            else:
                value = line

        else:
            value += "\n" + line
            key = buffer
            body = False

        value = unquote(value.strip(), encoding="UTF-8")

        if ": " in line and key in result:
            backup = result[key]

            if isinstance(backup, str):
                result[key] = [backup, value]
            else:
                result[key] = [*backup, value]
        else:
            result[key] = value.strip()

    return result
