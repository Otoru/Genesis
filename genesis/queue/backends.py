"""
Genesis queue backends
----------------------

Backend protocol and in-memory implementation for the queue abstraction.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Optional, Protocol, runtime_checkable

from genesis.exceptions import QueueTimeoutError


class _QueueState:
    """Per-queue state: FIFO deque, lock, condition; semaphore created on first acquire."""

    __slots__ = ("deque", "lock", "condition", "semaphore")

    def __init__(self) -> None:
        self.deque: deque[str] = deque()
        self.lock = asyncio.Lock()
        self.condition = asyncio.Condition(self.lock)
        self.semaphore: asyncio.Semaphore | None = None


@runtime_checkable
class QueueBackend(Protocol):
    """
    Protocol for queue backends.

    Implementations provide FIFO-ordered, concurrency-limited slots per queue_id.
    """

    async def enqueue(self, queue_id: str, item_id: str) -> None:
        """Add item_id to the tail of the queue."""
        ...

    async def wait_and_acquire(
        self,
        queue_id: str,
        item_id: str,
        max_concurrent: int,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Block until this item is at the head of the queue and a slot is free,
        then consume the head and hold one slot.

        If ``timeout`` is set (seconds) and expires before acquiring,
        remove this item from the queue and raise :exc:`QueueTimeoutError`.
        """
        ...

    async def release(self, queue_id: str) -> None:
        """Release one slot for the queue."""
        ...


class InMemoryBackend:
    """
    In-memory queue backend.

    Uses a deque and a semaphore per queue_id. Suitable for single-process use.
    """

    def __init__(self) -> None:
        """Initialize in-memory backend."""
        self._states: dict[str, _QueueState] = {}

    def _get_or_create_state(self, queue_id: str) -> _QueueState:
        """Get or create queue state (deque, lock, condition). Semaphore set in wait_and_acquire."""
        if queue_id not in self._states:
            self._states[queue_id] = _QueueState()
        return self._states[queue_id]

    async def enqueue(self, queue_id: str, item_id: str) -> None:
        """Add item_id to the tail of the queue."""
        state = self._get_or_create_state(queue_id)
        async with state.lock:
            state.deque.append(item_id)
            state.condition.notify_all()

    async def _wait_until_at_head(
        self,
        state: _QueueState,
        item_id: str,
        deadline: Optional[float],
    ) -> None:
        """Wait until item_id is at head of deque; on timeout remove item and raise."""
        while True:
            if state.deque and state.deque[0] == item_id:
                state.deque.popleft()
                state.condition.notify_all()
                return
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    try:
                        state.deque.remove(item_id)
                    except ValueError:
                        pass
                    state.condition.notify_all()
                    raise QueueTimeoutError()
            try:
                if remaining is not None:
                    await asyncio.wait_for(state.condition.wait(), timeout=remaining)
                else:
                    await state.condition.wait()
            except asyncio.TimeoutError:
                try:
                    state.deque.remove(item_id)
                except ValueError:
                    pass
                state.condition.notify_all()
                raise QueueTimeoutError()

    async def _acquire_semaphore(
        self, state: _QueueState, deadline: Optional[float]
    ) -> None:
        """Acquire one semaphore slot; raise QueueTimeoutError if deadline exceeded."""
        assert state.semaphore is not None  # set in wait_and_acquire before calling
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise QueueTimeoutError()
            try:
                await asyncio.wait_for(state.semaphore.acquire(), timeout=remaining)
            except asyncio.TimeoutError:
                raise QueueTimeoutError()
        else:
            await state.semaphore.acquire()

    async def wait_and_acquire(
        self,
        queue_id: str,
        item_id: str,
        max_concurrent: int,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Block until this item is at the head and a slot is free, then pop head and acquire.
        First call for a queue_id sets max_concurrent for that queue.
        If timeout (seconds) expires, remove item from queue and raise QueueTimeoutError.
        """
        state = self._get_or_create_state(queue_id)
        if state.semaphore is None:
            state.semaphore = asyncio.Semaphore(max_concurrent)
        deadline = time.monotonic() + timeout if timeout is not None else None
        async with state.lock:
            await self._wait_until_at_head(state, item_id, deadline)
        await self._acquire_semaphore(state, deadline)

    async def release(self, queue_id: str) -> None:
        """Release one slot for the queue."""
        if queue_id in self._states:
            state = self._states[queue_id]
            if state.semaphore is not None:
                state.semaphore.release()
            async with state.lock:
                state.condition.notify_all()
