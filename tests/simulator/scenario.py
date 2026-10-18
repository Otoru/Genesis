"""Scenario driver. Emits run from journal waits, not from a clock."""

import asyncio
from typing import Awaitable, Callable, Optional, Protocol, Sequence

from tests.simulator.codec import ESLFrame, Header
from tests.simulator.journal import CommandPredicate, Journal
from tests.simulator.messages import event_plain


class EventEmit(Protocol):
    """``Simulator.emit``."""

    def __call__(
        self,
        headers: Sequence[Header],
        *,
        body: bytes = b"",
        connection_id: Optional[str] = None,
    ) -> Awaitable[None]:
        """Deliver one event to the connections that accept it."""


Preempt = Callable[[str, ESLFrame], None]


class ScenarioDriver:
    """Queues an emit until a command has been observed."""

    def __init__(self, journal: Journal, emit: EventEmit) -> None:
        self._journal = journal
        self._emit = emit
        self._preempt: Optional[Preempt] = None

    def bind_preempt(self, preempt: Preempt) -> None:
        self._preempt = preempt

    async def emit_after_command(
        self,
        predicate: CommandPredicate,
        headers: Sequence[Header],
        *,
        body: bytes = b"",
        connection_id: Optional[str] = None,
        timeout: float = 2.0,
        registered: Optional[asyncio.Event] = None,
    ) -> None:
        wait = self._journal.register_command_wait(predicate)
        if registered is not None:
            registered.set()
        observed = await wait.wait(timeout)
        target = connection_id if connection_id is not None else observed.connection_id
        await self._emit(headers, body=body, connection_id=target)

    def before_reply(
        self,
        connection_id: str,
        headers: Sequence[Header],
        body: bytes = b"",
    ) -> None:
        if self._preempt is None:
            raise RuntimeError("scenario preempt is not bound")
        self._preempt(connection_id, event_plain(headers, body))
