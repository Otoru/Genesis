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
    personalization = ""
    result = {}
    buffer = ""
    value = ""

    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            buffer = key

        elif "Content-Type" in result and result["Content-Type"] == "api/response":
            personalization += "\n" + line
            key = "X-API-Reply-Text"
            value = personalization

        elif "Content-Type" in result and result["Content-Type"] == "text/event-plain":
            personalization += "\n" + line
            key = "X-Event-Content-Text"
            value = personalization

        else:
            key = buffer
            value += "\n" + line

        key = key.strip()
        value = value.strip()

        if ": " in line and key in result:
            backup = result[key]

            if isinstance(backup, str):
                result[key] = [backup, value]
            else:
                result[key] = [*backup, value]

        else:
            result[key] = value.strip()

    return result
