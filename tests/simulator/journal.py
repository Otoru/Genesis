"""In-memory command and event journal for the ESL simulator.

Waits are ``asyncio.Event`` objects. Register the wait before the
observation, or register it after the matching record is already in the
history. A wait that times out or is cancelled is removed. Command and
event ``sequence`` values count each stream on its own; callers that need
wire order use the connection write queue. This module does not sleep and
does not open a socket.
"""

import asyncio
from typing import Callable, Generic, List, Optional, Sequence, Tuple, TypeVar

from tests.simulator.codec import ESLFrame


class ObservedCommand:
    """One command line observed on a connection, in arrival order."""

    def __init__(self, connection_id: str, text: str, sequence: int) -> None:
        self.connection_id = connection_id
        self.text = text
        self.sequence = sequence

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ObservedCommand):
            return NotImplemented
        return (
            self.connection_id == other.connection_id
            and self.text == other.text
            and self.sequence == other.sequence
        )

    def __repr__(self) -> str:
        return "ObservedCommand(connection_id=%r, text=%r, sequence=%r)" % (
            self.connection_id,
            self.text,
            self.sequence,
        )


class ObservedEvent:
    """One decoded ESL frame observed on a connection, in arrival order."""

    def __init__(self, connection_id: str, frame: ESLFrame, sequence: int) -> None:
        self.connection_id = connection_id
        self.frame = frame
        self.sequence = sequence

    def __repr__(self) -> str:
        return "ObservedEvent(connection_id=%r, frame=%r, sequence=%r)" % (
            self.connection_id,
            self.frame,
            self.sequence,
        )


ItemT = TypeVar("ItemT")
CommandPredicate = Callable[[ObservedCommand], bool]
EventPredicate = Callable[[ObservedEvent], bool]


class Wait(Generic[ItemT]):
    """A one-shot wait. ``wait`` returns the first matching item.

    A timeout or cancellation drops the wait. A later record does not
    satisfy it, and it does not stay in the journal's pending list.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._match: Optional[ItemT] = None
        self._abandoned = False
        self._on_abandon: Optional[Callable[[], None]] = None

    @property
    def abandoned(self) -> bool:
        return self._abandoned

    def bind_abandon(self, callback: Callable[[], None]) -> None:
        self._on_abandon = callback

    def offer(self, item: ItemT) -> bool:
        if self._abandoned or self._match is not None:
            return False
        self._match = item
        self._event.set()
        return True

    def abandon(self) -> None:
        if self._abandoned or self._match is not None:
            return
        self._abandoned = True
        callback = self._on_abandon
        self._on_abandon = None
        if callback is not None:
            callback()

    async def wait(self, timeout: float) -> ItemT:
        if self._abandoned:
            raise asyncio.TimeoutError
        if not self._event.is_set():
            try:
                await asyncio.wait_for(self._event.wait(), timeout)
            except asyncio.CancelledError:
                self.abandon()
                raise
            except asyncio.TimeoutError:
                self.abandon()
                raise
        match = self._match
        if match is None:
            raise RuntimeError("wait signaled without a match")
        return match


class Journal:
    """Ordered command and event history, with condition waits."""

    def __init__(self) -> None:
        self._commands: List[ObservedCommand] = []
        self._events: List[ObservedEvent] = []
        self._command_waits: List[Tuple[CommandPredicate, Wait[ObservedCommand]]] = []
        self._event_waits: List[Tuple[EventPredicate, Wait[ObservedEvent]]] = []

    def commands(
        self, connection_id: Optional[str] = None
    ) -> Tuple[ObservedCommand, ...]:
        if connection_id is None:
            return tuple(self._commands)
        return tuple(
            item for item in self._commands if item.connection_id == connection_id
        )

    def events(self, connection_id: Optional[str] = None) -> Tuple[ObservedEvent, ...]:
        if connection_id is None:
            return tuple(self._events)
        return tuple(
            item for item in self._events if item.connection_id == connection_id
        )

    def record_command(self, connection_id: str, text: str) -> ObservedCommand:
        observed = ObservedCommand(connection_id, text, len(self._commands))
        self._commands.append(observed)
        self._signal(self._command_waits, observed)
        return observed

    def record_event(self, connection_id: str, frame: ESLFrame) -> ObservedEvent:
        observed = ObservedEvent(connection_id, frame, len(self._events))
        self._events.append(observed)
        self._signal(self._event_waits, observed)
        return observed

    def register_command_wait(
        self, predicate: CommandPredicate
    ) -> Wait[ObservedCommand]:
        return _register(self._commands, self._command_waits, predicate)

    def register_event_wait(self, predicate: EventPredicate) -> Wait[ObservedEvent]:
        return _register(self._events, self._event_waits, predicate)

    def _signal(
        self,
        waits: List[Tuple[Callable[[ItemT], bool], Wait[ItemT]]],
        item: ItemT,
    ) -> None:
        pending: List[Tuple[Callable[[ItemT], bool], Wait[ItemT]]] = []
        for predicate, wait in waits:
            if wait.abandoned:
                continue
            if predicate(item):
                wait.offer(item)
                continue
            pending.append((predicate, wait))
        waits[:] = pending


def _register(
    history: Sequence[ItemT],
    waits: List[Tuple[Callable[[ItemT], bool], Wait[ItemT]]],
    predicate: Callable[[ItemT], bool],
) -> Wait[ItemT]:
    wait: Wait[ItemT] = Wait()

    def abandon() -> None:
        waits[:] = [pair for pair in waits if pair[1] is not wait]

    wait.bind_abandon(abandon)
    for item in history:
        if predicate(item) and wait.offer(item):
            return wait
    waits.append((predicate, wait))
    return wait
