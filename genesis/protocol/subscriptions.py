"""Per-connection record of accepted ESL event subscriptions.

``event`` names are additive. Positive filters OR. A negative filter can
veto a later positive one. This ledger only remembers commands whose
reply started with ``+OK``, and it only removes names or filters that a
channel lease added itself.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any, Iterator, List, Optional, Sequence, Tuple

from genesis.exceptions import (
    ChannelError,
    CommandStage,
    ConnectionError,
    ConnectionLost,
    UnconnectedError,
)
from genesis.protocol.parser import ESLEvent

OBSERVED_EVENTS: Tuple[str, ...] = (
    "CHANNEL_STATE",
    "CHANNEL_ANSWER",
    "CHANNEL_EXECUTE",
    "CHANNEL_EXECUTE_COMPLETE",
    "CHANNEL_HANGUP",
    "CHANNEL_HANGUP_COMPLETE",
    "CHANNEL_DESTROY",
)

Filter = Tuple[str, str]


def _accepted(reply: ESLEvent) -> bool:
    text = reply.get("Reply-Text")
    if isinstance(text, list):
        text = text[0] if text else ""
    return isinstance(text, str) and text.startswith("+OK")


def _polarity(stored: str) -> Tuple[bool, str]:
    index = 0
    positive = True
    while index < len(stored):
        char = stored[index]
        if char == "+":
            positive = True
        elif char == "-":
            positive = False
        elif char != " ":
            break
        index += 1
    return positive, stored[index:]


def _matches(stored: str, actual: str, needle: str) -> bool:
    if stored.startswith("/"):
        try:
            return re.search(needle, actual) is not None
        except re.error:
            return False
    return actual.lower() == needle.lower()


def _filters_allow(filters: Sequence[Filter], fields: dict[str, str]) -> bool:
    """Positive filters OR. A matching negative filter vetoes the event."""
    if not filters:
        return True
    send = False
    for name, stored in filters:
        actual = fields.get(name.lower())
        if actual is None:
            continue
        positive, needle = _polarity(stored)
        if send and positive:
            continue
        if needle == "":
            continue
        if not _matches(stored, actual, needle):
            continue
        if positive:
            send = True
        else:
            return False
    return send


def _negative_veto(filters: Sequence[Filter], fields: dict[str, str]) -> bool:
    for name, stored in filters:
        actual = fields.get(name.lower())
        if actual is None:
            continue
        positive, needle = _polarity(stored)
        if positive or needle == "":
            continue
        if _matches(stored, actual, needle):
            return True
    return False


class EventLease:
    """Names and Unique-ID filters one recovery holds on a connection."""

    def __init__(
        self,
        ledger: "SubscriptionLedger",
        names: Tuple[str, ...],
        filters: Tuple[str, ...],
    ) -> None:
        self._ledger = ledger
        self._names = names
        self._filters = filters
        self._released = False

    async def release(self, protocol: Any) -> None:
        """Drop this hold. Nix or delete only what no other hold still needs."""
        if self._released:
            return
        self._released = True
        commands = self._ledger.release_interest(self._names, self._filters)
        if not commands:
            return
        try:
            protocol.raise_if_lost(CommandStage.NOT_SENT)
        except ConnectionLost:
            return
        for command in commands:
            try:
                await protocol.send(command)
            except ConnectionLost:
                return
            except (ConnectionError, UnconnectedError):
                return


class SubscriptionLedger:
    """Subscriptions observed from accepted commands on one connection."""

    def __init__(self) -> None:
        self.all_events = False
        self.myevents = False
        self.names: set[str] = set()
        self.external_names: set[str] = set()
        self.filters: List[Filter] = []
        self.external_filters: set[Filter] = set()
        self._holds: dict[str, int] = {}
        self._filter_holds: dict[str, int] = {}
        self._leasing = False

    @contextlib.contextmanager
    def leasing(self) -> Iterator[None]:
        """Mark the next accepted command as one this ledger sent."""
        self._leasing = True
        try:
            yield
        finally:
            self._leasing = False

    def observe(self, command: str, reply: ESLEvent) -> None:
        """Update server state from one accepted command. ``-ERR`` is ignored."""
        if not _accepted(reply):
            return
        first = command.splitlines()[0] if command else ""
        parts = first.split()
        if not parts:
            return
        verb = parts[0].lower()
        if verb == "events":
            verb = "event"
        if verb == "event":
            self._observe_event(parts[1:])
            return
        if verb == "nixevent":
            self._observe_nix(parts[1:])
            return
        if verb == "noevents":
            self.all_events = False
            self.myevents = False
            self.names.clear()
            self.external_names.clear()
            return
        if verb == "myevents":
            self.myevents = True
            return
        if verb == "filter":
            self._observe_filter(parts)

    def missing(self, needed: Sequence[str]) -> List[str]:
        """Event names that are not already enabled on this connection."""
        if self.all_events or self.myevents:
            return []
        return [name for name in needed if name not in self.names]

    def should_send_uuid_filter(self, channel_uuid: str) -> bool:
        """Add ``Unique-ID`` only when positive filters would otherwise hide us.

        An unfiltered connection already delivers every subscribed event.
        A ``Unique-ID`` filter there would be the only positive filter and
        would drop everyone else's events. A negative veto cannot be undone
        without deleting somebody else's filter, so it is left in place.
        """
        if not self.filters or self.negative_blocks(channel_uuid):
            return False
        if ("Unique-ID", channel_uuid) in self.filters:
            return False
        return not self._allows(channel_uuid)

    def negative_blocks(self, channel_uuid: str) -> bool:
        return any(
            _negative_veto(self.filters, _event_fields(name, channel_uuid))
            for name in OBSERVED_EVENTS
        )

    def suppresses_completion(self, channel_uuid: str) -> bool:
        """True when a negative filter drops ``CHANNEL_EXECUTE_COMPLETE``.

        Only ``Event-Name`` and ``Unique-ID`` are visible. A negative filter
        on another header is not detected and is not deleted.
        """
        return _negative_veto(
            self.filters, _event_fields("CHANNEL_EXECUTE_COMPLETE", channel_uuid)
        )

    def require_completion_visible(self, channel_uuid: str) -> None:
        """Refuse a blocking wait that cannot see completion. Filters stay."""
        if self.suppresses_completion(channel_uuid):
            raise ChannelError("negative filter suppresses CHANNEL_EXECUTE_COMPLETE")

    def hold(self, needed: Sequence[str], channel_uuid: str) -> EventLease:
        """Count one more user of names and filters this ledger owns."""
        held_names: List[str] = []
        if not self.all_events and not self.myevents:
            for name in needed:
                if name in self.external_names or name not in self.names:
                    continue
                self._holds[name] = self._holds.get(name, 0) + 1
                held_names.append(name)
        held_filters: List[str] = []
        key = ("Unique-ID", channel_uuid)
        if key in self.filters and key not in self.external_filters:
            self._filter_holds[channel_uuid] = (
                self._filter_holds.get(channel_uuid, 0) + 1
            )
            held_filters.append(channel_uuid)
        return EventLease(self, tuple(held_names), tuple(held_filters))

    def release_interest(
        self, names: Sequence[str], filters: Sequence[str]
    ) -> List[str]:
        """Return the undo commands for holds that just hit zero."""
        commands: List[str] = []
        nix: List[str] = []
        for name in names:
            remaining = self._holds.get(name, 0) - 1
            if remaining > 0:
                self._holds[name] = remaining
                continue
            self._holds.pop(name, None)
            if (
                not self.all_events
                and not self.myevents
                and name in self.names
                and name not in self.external_names
            ):
                nix.append(name)
        if nix:
            commands.append("nixevent " + " ".join(nix))
        for channel_uuid in filters:
            remaining = self._filter_holds.get(channel_uuid, 0) - 1
            if remaining > 0:
                self._filter_holds[channel_uuid] = remaining
                continue
            self._filter_holds.pop(channel_uuid, None)
            key = ("Unique-ID", channel_uuid)
            if key in self.filters and key not in self.external_filters:
                commands.append("filter delete Unique-ID %s" % channel_uuid)
        return commands

    def _allows(self, channel_uuid: str) -> bool:
        return all(
            _filters_allow(self.filters, _event_fields(name, channel_uuid))
            for name in OBSERVED_EVENTS
        )

    def _observe_event(self, tokens: Sequence[str]) -> None:
        parts = list(tokens)
        if parts and parts[0].lower() == "plain":
            parts = parts[1:]
        custom = False
        for token in parts:
            if custom:
                custom = False
                continue
            upper = token.upper()
            if upper == "CUSTOM":
                custom = True
                continue
            if upper == "ALL":
                self.all_events = True
                continue
            self.names.add(upper)
            if not self._leasing:
                self.external_names.add(upper)

    def _observe_nix(self, tokens: Sequence[str]) -> None:
        for token in tokens:
            upper = token.upper()
            if upper == "ALL":
                self.all_events = False
                self.myevents = False
                self.names.clear()
                self.external_names.clear()
                continue
            self.names.discard(upper)
            self.external_names.discard(upper)

    def _observe_filter(self, parts: Sequence[str]) -> None:
        if len(parts) < 3:
            return
        if parts[1].lower() == "delete":
            if parts[2].lower() == "all":
                self.filters.clear()
                self.external_filters.clear()
                return
            if len(parts) < 4:
                return
            key = (parts[2], parts[3])
            self.filters = [item for item in self.filters if item != key]
            self.external_filters.discard(key)
            return
        added = _added_filter(parts)
        if added is None:
            return
        self.filters.append(added)
        if not self._leasing:
            self.external_filters.add(added)


def _added_filter(parts: Sequence[str]) -> Optional[Filter]:
    if parts[1].lower() == "add":
        if len(parts) < 4:
            return None
        return (parts[2], parts[3])
    return (parts[1], parts[2])


def _event_fields(event_name: str, channel_uuid: str) -> dict[str, str]:
    return {"event-name": event_name, "unique-id": channel_uuid}


async def ensure_channel_events(protocol: Any, channel_uuid: str) -> EventLease:
    """Subscribe to the channel events this recovery needs, then hold them.

    ``myevents`` is not sent. Names already enabled, including ``ALL``, are
    left alone. A failed ack raises ``ChannelError`` and holds nothing.
    """
    ledger: SubscriptionLedger = protocol.subscriptions
    missing = ledger.missing(OBSERVED_EVENTS)
    if missing:
        with ledger.leasing():
            reply = await protocol.send("event plain " + " ".join(missing))
        if not _accepted(reply):
            raise ChannelError("event subscription was not accepted")
    if ledger.should_send_uuid_filter(channel_uuid):
        with ledger.leasing():
            reply = await protocol.send("filter Unique-ID %s" % channel_uuid)
        if not _accepted(reply):
            raise ChannelError("channel filter was not accepted")
    return ledger.hold(OBSERVED_EVENTS, channel_uuid)
