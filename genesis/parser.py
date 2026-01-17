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
        self._raw_data = {}
        super().__init__(*args, **kwargs)
        self.body: Optional[str] = None

    def __getitem__(self, key):
        if key in self._raw_data:
            raw = self._raw_data.pop(key)
            if isinstance(raw, list):
                val = [unquote(r, encoding="UTF-8") for r in raw]
            else:
                val = unquote(raw, encoding="UTF-8")
            self.data[key] = val

        return super().__getitem__(key)

    def __contains__(self, key):
        return key in self.data or key in self._raw_data

    def __iter__(self):
        # Iterate over a snapshot of keys to allow modification (lazy loading) during iteration
        keys = set(self.data.keys()) | set(self._raw_data.keys())
        yield from keys

    def __len__(self):
        # We need to be careful not to double count if a key is in both (though the logic tries to avoid that)
        return len(set(self.data.keys()) | set(self._raw_data.keys()))

    def __repr__(self):
        # To provide a correct representation, we might need to decode everything or show raw.
        # For debugging/equality, usually we want the full dictionary view.
        # This effectively eagerly loads everything if you print it, but that's acceptable for debugging.
        dict_view = dict(self.items())
        return repr(dict_view)

    def __delitem__(self, key):
        if key in self._raw_data:
            del self._raw_data[key]
        super().__delitem__(key)

    def set_raw_header(self, key, value):
        """
        Used for multiline headers where we want to update the entry with the accumulated value.
        This invalidates any cached decoded value.
        """
        if key in self.data:
            del self.data[key]
        self._raw_data[key] = value

    def add_raw_header(self, key, value):
        """
        We assume 'key' is already unquoted by the parser.
        """
        if key in self.data:
            # Already decoded or added as clean
            current = self.data[key]
            decoded_new = unquote(value, encoding="UTF-8")
            if isinstance(current, list):
                current.append(decoded_new)
            else:
                self.data[key] = [current, decoded_new]
        elif key in self._raw_data:
            # Existing raw entry
            current = self._raw_data[key]
            if isinstance(current, list):
                current.append(value)
            else:
                self._raw_data[key] = [current, value]
        else:
            self._raw_data[key] = value


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

        # We MUST unquote the key immediately because it is used for lookup
        key = unquote(key.strip(), encoding="UTF-8")
        raw_value = value.strip()

        if ": " in line:
            # Potential new header or repeated header
            headers.add_raw_header(key, raw_value)
        else:
            # Continuation of previous header -> Overwrite
            headers.set_raw_header(key, raw_value)

    return headers
