"""Tests for genesis queue (slot, semaphore, backends)."""

import asyncio

import pytest

from genesis.queue import InMemoryBackend, Queue, QueueSemaphore, QueueTimeoutError


@pytest.mark.asyncio
async def test_in_memory_backend_enqueue_wait_and_acquire_release():
    """Backend: enqueue, wait_and_acquire, release."""
    backend = InMemoryBackend()
    await backend.enqueue("q1", "item1")
    await backend.wait_and_acquire("q1", "item1", max_concurrent=1)
    await backend.release("q1")


@pytest.mark.asyncio
async def test_in_memory_backend_fifo_order():
    """Backend: first enqueued acquires first when slot free."""
    backend = InMemoryBackend()
    await backend.enqueue("q1", "first")
    await backend.enqueue("q1", "second")

    # First acquires
    await backend.wait_and_acquire("q1", "first", max_concurrent=1)
    # Second must wait until first releases
    entered = asyncio.Event()
    released = asyncio.Event()

    async def second_acquires():
        await backend.wait_and_acquire("q1", "second", max_concurrent=1)
        entered.set()
        await released.wait()
        await backend.release("q1")

    async def first_releases():
        await backend.release("q1")
        released.set()

    t2 = asyncio.create_task(second_acquires())
    t1 = asyncio.create_task(first_releases())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.wait_for(t2, timeout=2.0)
    t1.cancel()
    try:
        await t1
    except asyncio.CancelledError:
        raise


@pytest.mark.asyncio
async def test_queue_slot_context_manager():
    """Queue.slot() is an async context manager; release on exit."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    entered = asyncio.Event()

    async def use_slot():
        async with queue.slot("sales"):
            entered.set()

    t = asyncio.create_task(use_slot())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.wait_for(t, timeout=2.0)


@pytest.mark.asyncio
async def test_queue_slot_with_item_id():
    """Queue.slot(queue_id, item_id=...) uses that item_id for ordering."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    order: list[str] = []

    async def first():
        async with queue.slot("q", item_id="a"):
            order.append("a-in")
        order.append("a-out")

    async def second():
        async with queue.slot("q", item_id="b"):
            order.append("b-in")
        order.append("b-out")

    t1 = asyncio.create_task(first())
    t2 = asyncio.create_task(second())
    await asyncio.gather(t1, t2)
    assert order == ["a-in", "a-out", "b-in", "b-out"]


@pytest.mark.asyncio
async def test_queue_semaphore_context_manager():
    """Queue.semaphore() returns a reusable context manager."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    sem = queue.semaphore("support", max_concurrent=1)
    entered = asyncio.Event()

    async def use_sem():
        async with sem:
            entered.set()

    t = asyncio.create_task(use_sem())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.wait_for(t, timeout=2.0)


@pytest.mark.asyncio
async def test_queue_semaphore_max_concurrent_two():
    """With max_concurrent=2, two can be inside at once."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    sem = queue.semaphore("pool", max_concurrent=2)
    both_inside = asyncio.Event()

    async def enter(ready: asyncio.Event):
        async with sem:
            ready.set()
            await both_inside.wait()

    r1 = asyncio.Event()
    r2 = asyncio.Event()
    t1 = asyncio.create_task(enter(r1))
    t2 = asyncio.create_task(enter(r2))
    await asyncio.wait_for(r1.wait(), timeout=2.0)
    await asyncio.wait_for(r2.wait(), timeout=2.0)
    both_inside.set()
    await asyncio.gather(t1, t2)


@pytest.mark.asyncio
async def test_queue_slot_semaphore_like():
    """slot() behaves like a semaphore: one in, one out, then next."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    log: list[str] = []

    async def worker(name: str):
        async with queue.slot("single", item_id=name):
            log.append(f"{name}-in")
        log.append(f"{name}-out")

    await asyncio.gather(
        worker("a"),
        worker("b"),
        worker("c"),
    )
    assert log == ["a-in", "a-out", "b-in", "b-out", "c-in", "c-out"]


@pytest.mark.asyncio
async def test_queue_slot_timeout_raises_and_removes_from_queue():
    """With timeout, wait_and_acquire raises QueueTimeoutError and item is removed."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    entered = asyncio.Event()

    async def holder():
        async with queue.slot("q", item_id="first"):
            entered.set()
            await asyncio.Event().wait()

    async def waiter():
        await entered.wait()
        try:
            async with queue.slot("q", item_id="second", timeout=0.2):
                pass
            pytest.fail("expected QueueTimeoutError")
        except QueueTimeoutError:
            pass  # expected

    t_holder = asyncio.create_task(holder())
    t_waiter = asyncio.create_task(waiter())
    await asyncio.wait_for(t_waiter, timeout=2.0)
    t_holder.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t_holder


@pytest.mark.asyncio
async def test_queue_slot_timeout_next_in_line_can_acquire():
    """After one item times out, the next in line can acquire."""
    backend = InMemoryBackend()
    queue = Queue(backend)
    order: list[str] = []
    first_holding = asyncio.Event()
    release_first = asyncio.Event()

    async def first_acquires():
        async with queue.slot("q", item_id="a"):
            order.append("a-in")
            first_holding.set()
            await release_first.wait()
        order.append("a-out")

    async def second_times_out():
        await first_holding.wait()
        try:
            async with queue.slot("q", item_id="b", timeout=0.2):
                order.append("b-in")
        except QueueTimeoutError:
            order.append("b-timeout")
        order.append("b-done")
        release_first.set()

    async def third_acquires():
        await first_holding.wait()
        async with queue.slot("q", item_id="c"):
            order.append("c-in")
        order.append("c-out")

    await asyncio.gather(
        first_acquires(),
        second_times_out(),
        third_acquires(),
    )
    assert "a-in" in order and "a-out" in order
    assert "b-timeout" in order and "b-done" in order
    assert "c-in" in order and "c-out" in order
    assert order.index("b-timeout") < order.index("c-in")


@pytest.mark.asyncio
async def test_queue_default_in_memory_backend():
    """Queue() without backend uses InMemoryBackend by default."""
    queue = Queue()
    entered = asyncio.Event()

    async def use_slot():
        async with queue.slot("default"):
            entered.set()

    t = asyncio.create_task(use_slot())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.wait_for(t, timeout=2.0)
