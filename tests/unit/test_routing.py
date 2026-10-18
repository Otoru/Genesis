"""
Tests for routing strategies and dispatcher.
"""

import asyncio
import threading
from asyncio import Task
from typing import Any
from unittest.mock import MagicMock, patch

from genesis.protocol.parser import ESLEvent
from genesis.protocol.routing.channel import ChannelRoutingStrategy
from genesis.protocol.routing.composite import CompositeRoutingStrategy
from genesis.protocol.routing.dispatcher import dispatch_to_handlers, run_on_loop
from genesis.protocol.routing.global_ import GlobalRoutingStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(**kwargs: str) -> ESLEvent:
    event = ESLEvent()
    event.update(kwargs)
    return event


class _DispatchTaskSet(set[Task[Any]]):
    """Task set whose ``settled`` future follows the dispatcher done callback.

    Create the future and this set before ``dispatch_to_handlers``. ``add``
    runs while the task is queued, before the handler body. The dispatcher
    registers its own done callback after ``add``, so this hook schedules
    ``settled`` on the following loop turn, after that callback has discarded
    the task. Handler completion is a separate event.
    """

    def __init__(self, settled: asyncio.Future[None]) -> None:
        super().__init__()
        self._settled = settled

    def add(self, task: Task[Any]) -> None:
        super().add(task)

        def _schedule_after_dispatcher_callback(_finished: Task[Any]) -> None:
            def _mark_settled() -> None:
                if not self._settled.done():
                    self._settled.set_result(None)

            asyncio.get_running_loop().call_soon(_mark_settled)

        task.add_done_callback(_schedule_after_dispatcher_callback)


def _track_dispatcher_callback() -> tuple[_DispatchTaskSet, asyncio.Future[None]]:
    settled: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    return _DispatchTaskSet(settled), settled


# ---------------------------------------------------------------------------
# ChannelRoutingStrategy
# ---------------------------------------------------------------------------


async def test_channel_routing_match_returns_handlers_and_stops() -> None:
    uuid = "test-uuid-123"
    registry = {f"{uuid}:CHANNEL_STATE": [MagicMock()]}
    strategy = ChannelRoutingStrategy(registry)
    event = make_event(**{"Unique-ID": uuid, "Event-Name": "CHANNEL_STATE"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == registry[f"{uuid}:CHANNEL_STATE"]
    assert should_stop is True


async def test_channel_routing_miss_returns_empty_and_false() -> None:
    strategy = ChannelRoutingStrategy({})
    event = make_event(**{"Unique-ID": "unknown-uuid", "Event-Name": "CHANNEL_STATE"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


async def test_channel_routing_custom_event_uses_subclass() -> None:
    uuid = "abc"
    subclass = "mod_audio_stream::play"
    registry = {f"{uuid}:{subclass}": [MagicMock()]}
    strategy = ChannelRoutingStrategy(registry)
    event = make_event(
        **{"Unique-ID": uuid, "Event-Name": "CUSTOM", "Event-Subclass": subclass}
    )

    handlers, should_stop = await strategy.route(event)

    assert len(handlers) == 1
    assert should_stop is True


async def test_channel_routing_no_uuid_returns_empty() -> None:
    strategy = ChannelRoutingStrategy({"x:HEARTBEAT": [MagicMock()]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


# ---------------------------------------------------------------------------
# GlobalRoutingStrategy
# ---------------------------------------------------------------------------


async def test_global_routing_match_by_event_name() -> None:
    handler = MagicMock()
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [handler]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await strategy.route(event)

    assert handler in handlers
    assert should_stop is False


async def test_global_routing_wildcard_matches_any_event() -> None:
    wildcard = MagicMock()
    strategy = GlobalRoutingStrategy({"*": [wildcard]})
    event = make_event(**{"Event-Name": "CHANNEL_CREATE"})

    handlers, should_stop = await strategy.route(event)

    assert wildcard in handlers
    assert should_stop is False


async def test_global_routing_specific_and_wildcard_combined() -> None:
    specific = MagicMock()
    wildcard = MagicMock()
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [specific], "*": [wildcard]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, _ = await strategy.route(event)

    assert specific in handlers
    assert wildcard in handlers


async def test_global_routing_miss_returns_empty() -> None:
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [MagicMock()]})
    event = make_event(**{"Event-Name": "CHANNEL_HANGUP"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


async def test_global_routing_no_event_name_returns_empty() -> None:
    strategy = GlobalRoutingStrategy({"*": [MagicMock()]})
    event = ESLEvent()

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


# ---------------------------------------------------------------------------
# CompositeRoutingStrategy
# ---------------------------------------------------------------------------


async def test_composite_stops_at_first_strategy_with_handlers() -> None:
    h1 = MagicMock()
    h2 = MagicMock()
    uuid = "u1"
    channel_registry = {f"{uuid}:CHANNEL_STATE": [h1]}
    global_handlers = {"CHANNEL_STATE": [h2]}

    composite = CompositeRoutingStrategy(
        [
            ChannelRoutingStrategy(channel_registry),
            GlobalRoutingStrategy(global_handlers),
        ]
    )
    event = make_event(**{"Unique-ID": uuid, "Event-Name": "CHANNEL_STATE"})

    handlers, should_stop = await composite.route(event)

    assert h1 in handlers
    assert h2 not in handlers
    assert should_stop is True


async def test_composite_falls_through_to_next_strategy() -> None:
    h2 = MagicMock()
    composite = CompositeRoutingStrategy(
        [
            ChannelRoutingStrategy({}),
            GlobalRoutingStrategy({"HEARTBEAT": [h2]}),
        ]
    )
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await composite.route(event)

    assert h2 in handlers
    assert should_stop is False


async def test_composite_no_match_returns_empty() -> None:
    composite = CompositeRoutingStrategy(
        [
            ChannelRoutingStrategy({}),
            GlobalRoutingStrategy({}),
        ]
    )
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await composite.route(event)

    assert handlers == []
    assert should_stop is False


async def test_composite_propagates_should_stop_true() -> None:
    """A strategy returning (handlers, True) must propagate should_stop=True."""
    h = MagicMock()
    uuid = "u2"
    channel_registry = {f"{uuid}:CHANNEL_STATE": [h]}
    composite = CompositeRoutingStrategy(
        [
            ChannelRoutingStrategy(channel_registry),
        ]
    )
    event = make_event(**{"Unique-ID": uuid, "Event-Name": "CHANNEL_STATE"})

    _, should_stop = await composite.route(event)

    assert should_stop is True


# ---------------------------------------------------------------------------
# dispatch_to_handlers
# ---------------------------------------------------------------------------


async def test_dispatch_creates_tasks_in_set() -> None:
    done = asyncio.Event()

    async def handler(event: ESLEvent) -> None:
        done.set()

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([handler], event, task_set)

    # At least one task should be in the set immediately after dispatch
    assert len(task_set) == 1

    await asyncio.wait_for(done.wait(), timeout=5)


async def test_dispatch_task_removed_from_set_after_completion() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    task_set, removed = _track_dispatcher_callback()

    async def handler(event: ESLEvent) -> None:
        entered.set()
        await release.wait()

    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([handler], event, task_set)
    await asyncio.wait_for(entered.wait(), timeout=5)
    assert len(task_set) == 1
    release.set()
    await asyncio.wait_for(removed, timeout=5)

    assert len(task_set) == 0


async def test_dispatch_exception_in_handler_is_logged_not_propagated() -> None:
    task_set, removed = _track_dispatcher_callback()

    async def bad_handler(event: ESLEvent) -> None:
        raise ValueError("handler exploded")

    event = make_event(**{"Event-Name": "HEARTBEAT"})

    with patch("genesis.protocol.routing.dispatcher.logger") as mock_log:
        dispatch_to_handlers([bad_handler], event, task_set)
        tasks = list(task_set)
        for task in tasks:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except Exception:
                pass
        await asyncio.wait_for(removed, timeout=5)

    error_calls = mock_log.error.call_args_list
    assert any("handler exploded" in str(call) for call in error_calls)


async def test_dispatch_sync_handler_via_to_thread() -> None:
    results = []

    def sync_handler(event: ESLEvent) -> None:
        results.append(event.get("Event-Name"))

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([sync_handler], event, task_set)
    tasks = list(task_set)
    await asyncio.gather(*tasks)

    assert results == ["HEARTBEAT"]


async def test_dispatch_no_task_set_does_not_raise() -> None:
    """dispatch_to_handlers must work without a task_set (backwards compat)."""
    done = asyncio.Event()

    async def handler(event: ESLEvent) -> None:
        done.set()

    event = make_event(**{"Event-Name": "HEARTBEAT"})
    dispatch_to_handlers([handler], event)
    await asyncio.wait_for(done.wait(), timeout=5)


async def test_run_on_loop_handler_stays_on_the_owning_loop_thread() -> None:
    """Callbacks that complete a future must not run on the executor."""
    loop = asyncio.get_running_loop()
    owner = threading.get_ident()
    completed: asyncio.Future[int] = loop.create_future()
    worker_thread: asyncio.Future[int] = loop.create_future()

    def on_loop(event: ESLEvent) -> None:
        completed.set_result(threading.get_ident())

    def on_worker(event: ESLEvent) -> None:
        ident = threading.get_ident()
        loop.call_soon_threadsafe(worker_thread.set_result, ident)

    event = make_event(**{"Event-Name": "CHANNEL_EXECUTE_COMPLETE"})
    task_set: set[Task[Any]] = set()
    dispatch_to_handlers([run_on_loop(on_loop), on_worker], event, task_set)

    assert await asyncio.wait_for(completed, timeout=5) == owner
    assert await asyncio.wait_for(worker_thread, timeout=5) != owner


async def test_run_on_loop_handler_exception_is_logged() -> None:
    task_set, removed = _track_dispatcher_callback()

    def bad_handler(event: ESLEvent) -> None:
        raise ValueError("loop handler exploded")

    event = make_event(**{"Event-Name": "CHANNEL_EXECUTE_COMPLETE"})
    with patch("genesis.protocol.routing.dispatcher.logger") as mock_log:
        dispatch_to_handlers([run_on_loop(bad_handler)], event, task_set)
        await asyncio.wait_for(removed, timeout=5)

    error_calls = mock_log.error.call_args_list
    assert any("loop handler exploded" in str(call) for call in error_calls)
