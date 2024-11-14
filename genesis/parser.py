"""
Genesis parse
-------------
It implements the intelligence necessary for us to transform freeswitch events into python primitive types.
"""

from typing import Optional
from collections import UserDict
from urllib.parse import unquote


class ESLEvent(UserDict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body: Optional[str] = None


def parse_headers(payload: str) -> ESLEvent:
    lines = payload.strip().splitlines()
    headers = ESLEvent()
    buffer = ""
    value = ""

    for line in lines:
        if ": " in line:
            key, value = line.split(": ", 1)
            buffer = key

        else:
            value += "\n" + line
            key = buffer

        key = unquote(key.strip(), encoding="UTF-8")
        value = unquote(value.strip(), encoding="UTF-8")

        if ": " in line and key in headers:
            backup = headers[key]

            if isinstance(backup, str):
                headers[key] = [backup, value]
            else:
                headers[key] = [*backup, value]

        else:
            headers[key] = value

    return headers
