"""
Pending ESL command replies
---------------------------

FreeSWITCH 1.11.3 answers command/reply and api/response in FIFO order
with no correlation id. A caller cancelled after write() leaves a tombstone
so that reply is not delivered to a later caller.
"""

import asyncio
from collections import deque
from typing import Awaitable, Callable, Deque, Optional

from genesis.exceptions import CommandStage, ConnectionLost
from genesis.observability import logger
from genesis.protocol.parser import ESLEvent


class WriteEvidence:
    """``wrote`` is set immediately before ``StreamWriter.write``."""

    __slots__ = ("wrote",)

    def __init__(self) -> None:
        self.wrote = False


class _Slot:
    __slots__ = ("future",)

    def __init__(self, future: Optional["asyncio.Future[ESLEvent]"]) -> None:
        self.future = future


class CommandExchange:
    """One FIFO of in-flight commands for a single connection."""

    def __init__(self, flush: Optional[Callable[[], Awaitable[None]]] = None) -> None:
        self._slots: Deque[_Slot] = deque()
        self._lock = asyncio.Lock()
        self._flush = flush
        self._write_failure: Optional[BaseException] = None
        self.closed = False

    @property
    def depth(self) -> int:
        return len(self._slots)

    def take_write_failure(self) -> Optional[BaseException]:
        """Return a post-write error whose reply was still delivered."""
        failure = self._write_failure
        self._write_failure = None
        return failure

    def close(self) -> None:
        """Reject new commands. Replies already read can still be delivered."""
        self.closed = True

    async def exchange(
        self, transmit: Callable[[WriteEvidence], Awaitable[None]]
    ) -> ESLEvent:
        """Write one command and wait for its reply."""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[ESLEvent] = loop.create_future()
        slot = _Slot(future)
        evidence = WriteEvidence()

        async with self._lock:
            if self.closed:
                raise ConnectionLost(CommandStage.NOT_SENT)
            self._slots.append(slot)
            try:
                await transmit(evidence)
            except asyncio.CancelledError:
                if evidence.wrote:
                    slot.future = None
                else:
                    self._discard(slot)
                raise
            except Exception as exc:
                if not evidence.wrote:
                    self._discard(slot)
                    if self.closed:
                        raise ConnectionLost(CommandStage.NOT_SENT) from exc
                    raise
                try:
                    if self._flush is not None:
                        await self._flush()
                except asyncio.CancelledError:
                    if not future.done():
                        slot.future = None
                    raise
                if future.done():
                    self._write_failure = exc
                    return future.result()
                self._discard(slot)
                self.fail_pending()
                raise ConnectionLost(CommandStage.UNCONFIRMED) from exc

        try:
            return await future
        except asyncio.CancelledError:
            slot.future = None
            raise

    def deliver(self, event: ESLEvent) -> None:
        """Give ``event`` to the oldest slot. A tombstone discards that reply."""
        if not self._slots:
            logger.debug("ESL reply with no pending command.")
            return
        slot = self._slots.popleft()
        future = slot.future
        if future is None or future.done():
            return
        future.set_result(event)

    def fail_pending(self) -> None:
        """Fail live waiters. Tombstones are dropped."""
        self.closed = True
        pending = list(self._slots)
        self._slots.clear()
        for slot in pending:
            future = slot.future
            slot.future = None
            if future is not None and not future.done():
                future.set_exception(ConnectionLost(CommandStage.UNCONFIRMED))

    def _discard(self, slot: _Slot) -> None:
        try:
            self._slots.remove(slot)
        except ValueError:
            pass
