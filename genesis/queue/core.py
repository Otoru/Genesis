"""
Genesis queue core
------------------

Queue abstraction with context-manager and semaphore-like API.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Optional
from uuid import uuid4

from opentelemetry import metrics, trace

from genesis.queue.backends import InMemoryBackend, QueueBackend

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

queue_operations_counter = meter.create_counter(
    "genesis.queue.operations",
    description="Queue slot acquire/release operations",
    unit="1",
)
queue_wait_duration = meter.create_histogram(
    "genesis.queue.wait_duration",
    description="Time spent waiting for a slot",
    unit="s",
)


class QueueSlot:
    """
    Async context manager for a single slot acquisition.

    Use via ``async with queue.slot(queue_id):``. On enter, enqueues and blocks
    until this item is at the head and a slot is free; on exit, releases the slot.
    Optional ``timeout`` (seconds): raise :exc:`~genesis.exceptions.QueueTimeoutError` if not acquired in time.
    """

    __slots__ = (
        "_queue",
        "_queue_id",
        "_item_id",
        "_max_concurrent",
        "_timeout",
        "_acquired",
        "_released",
    )

    def __init__(
        self,
        queue: "Queue",
        queue_id: str,
        *,
        item_id: Optional[str] = None,
        max_concurrent: int = 1,
        timeout: Optional[float] = None,
    ) -> None:
        self._queue = queue
        self._queue_id = queue_id
        self._item_id = item_id or str(uuid4())
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._acquired = False
        self._released = False

    async def __aenter__(self) -> "QueueSlot":
        await self._queue._enqueue(self._queue_id, self._item_id)
        start = time.monotonic()
        with tracer.start_as_current_span(
            "queue.wait_and_acquire",
            attributes={
                "queue.id": self._queue_id,
                "queue.item_id": self._item_id,
            },
        ):
            await self._queue._backend.wait_and_acquire(
                self._queue_id,
                self._item_id,
                self._max_concurrent,
                timeout=self._timeout,
            )
        self._acquired = True
        elapsed = time.monotonic() - start
        queue_wait_duration.record(elapsed, attributes={"queue.id": self._queue_id})
        queue_operations_counter.add(
            1, attributes={"queue.id": self._queue_id, "op": "acquire"}
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._acquired and not self._released:
            self._released = True
            await self._queue._release(self._queue_id)
            queue_operations_counter.add(
                1, attributes={"queue.id": self._queue_id, "op": "release"}
            )


class QueueSemaphore:
    """
    Semaphore-like handle for a queue: reusable context manager for the same queue_id.

    Use via ``async with queue.semaphore(queue_id):`` or store and reuse:
    ``sem = queue.semaphore("sales", max_concurrent=2); async with sem: ...``
    Optional ``timeout`` (seconds) applies to each acquire.
    """

    __slots__ = ("_queue", "_queue_id", "_max_concurrent", "_timeout", "_slot")

    def __init__(
        self,
        queue: "Queue",
        queue_id: str,
        max_concurrent: int = 1,
        timeout: Optional[float] = None,
    ) -> None:
        self._queue = queue
        self._queue_id = queue_id
        self._max_concurrent = max_concurrent
        self._timeout = timeout
        self._slot: Optional[QueueSlot] = None

    @asynccontextmanager
    async def __call__(self, *, item_id: Optional[str] = None):
        """Acquire a slot with optional item_id (e.g. session uuid)."""
        slot = QueueSlot(
            self._queue,
            self._queue_id,
            item_id=item_id,
            max_concurrent=self._max_concurrent,
            timeout=self._timeout,
        )
        async with slot:
            yield

    async def __aenter__(self) -> "QueueSemaphore":
        self._slot = QueueSlot(
            self._queue,
            self._queue_id,
            max_concurrent=self._max_concurrent,
            timeout=self._timeout,
        )
        await self._slot.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._slot is not None:
            await self._slot.__aexit__(*args)
            self._slot = None


class Queue:
    """
    FIFO queue with concurrency limit per queue_id.

    Uses an in-memory backend by default; pass a backend for Redis or custom
    storage. API is context-manager and semaphore-like:
    ``async with queue.slot("sales"):`` or
    ``sem = queue.semaphore("sales", max_concurrent=2); async with sem: ...``
    """

    __slots__ = ("_backend",)

    def __init__(self, backend: Optional[QueueBackend] = None) -> None:
        self._backend = backend if backend is not None else InMemoryBackend()

    def slot(
        self,
        queue_id: str,
        *,
        item_id: Optional[str] = None,
        max_concurrent: int = 1,
        timeout: Optional[float] = None,
    ) -> QueueSlot:
        """
        Return a context manager that acquires a slot in the given queue.

        On enter: enqueue (with optional item_id), then block until at head and
        a slot is free. On exit: release the slot.
        If ``timeout`` (seconds) is set and expires before acquiring,
        the item is removed from the queue and :exc:`~genesis.exceptions.QueueTimeoutError` is raised.
        """
        return QueueSlot(
            self,
            queue_id,
            item_id=item_id,
            max_concurrent=max_concurrent,
            timeout=timeout,
        )

    def semaphore(
        self,
        queue_id: str,
        max_concurrent: int = 1,
        timeout: Optional[float] = None,
    ) -> QueueSemaphore:
        """
        Return a semaphore-like handle for the queue. Reusable for multiple
        ``async with sem:`` calls with the same concurrency limit.
        Optional ``timeout`` (seconds) applies to each acquire.
        """
        return QueueSemaphore(
            self, queue_id, max_concurrent=max_concurrent, timeout=timeout
        )

    async def _enqueue(self, queue_id: str, item_id: str) -> None:
        await self._backend.enqueue(queue_id, item_id)

    async def _release(self, queue_id: str) -> None:
        await self._backend.release(queue_id)
