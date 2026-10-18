"""In-memory channel rows for exists and dump.

A row is scenario state. It is not a dialplan, a media path, or an event
buffer. Dump text is rendered from the row at the moment of the lookup.
"""

from typing import Dict, List, Optional, Tuple

from tests.simulator.messages import url_encode

HeaderValue = Tuple[str, str]


class ChannelRecord:
    """Fields a later ``uuid_dump`` can render. Lookup policy lives here too."""

    def __init__(
        self,
        channel_uuid: str,
        *,
        name: str = "",
        state: str = "CS_EXECUTE",
        call_state: str = "ACTIVE",
        answer_state: str = "answered",
        application: str = "",
        application_data: str = "",
        variables: Optional[Dict[str, str]] = None,
    ) -> None:
        self.channel_uuid = channel_uuid
        self.name = name
        self.state = state
        self.call_state = call_state
        self.answer_state = answer_state
        self.application = application
        self.application_data = application_data
        self.variables: Dict[str, str] = dict(variables or {})
        self.sequence = 0
        self.lookups_remaining: Optional[int] = None

    def take_dump_fields(self) -> Tuple[HeaderValue, ...]:
        """One dump's fields. ``Event-Sequence`` advances on each call."""
        self.sequence += 1
        rows: List[HeaderValue] = [
            ("Event-Name", "CHANNEL_DATA"),
            ("Unique-ID", self.channel_uuid),
            ("Channel-State", self.state),
            ("Channel-Call-State", self.call_state),
            ("Answer-State", self.answer_state),
        ]
        if self.name:
            rows.append(("Channel-Name", self.name))
        if self.application:
            rows.append(("variable_current_application", self.application))
        if self.application_data:
            rows.append(("variable_current_application_data", self.application_data))
        for key in sorted(self.variables):
            rows.append((key, self.variables[key]))
        rows.append(("Event-Sequence", str(self.sequence)))
        return tuple(rows)


def render_dump(record: ChannelRecord, *, plain: bool = False) -> bytes:
    """Serialize one dump body.

    Default and ``txt`` percent-encode values. ``plain`` wraps each value in
    brackets and does not percent-encode. The default is txt.
    """
    lines: List[str] = []
    for name, value in record.take_dump_fields():
        if plain:
            rendered = "[%s]" % value
        else:
            rendered = url_encode(value)
        lines.append("%s: %s\n" % (name, rendered))
    lines.append("\n")
    return "".join(lines).encode("utf-8")
