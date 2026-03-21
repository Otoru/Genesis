"""
Tests for routing strategies and dispatcher.
"""

import asyncio
import logging
from asyncio import Task
from typing import Any
from unittest.mock import MagicMock

import pytest

from genesis.protocol.parser import ESLEvent
from genesis.protocol.routing.channel import ChannelRoutingStrategy
from genesis.protocol.routing.global_ import GlobalRoutingStrategy
from genesis.protocol.routing.composite import CompositeRoutingStrategy
from genesis.protocol.routing.dispatcher import dispatch_to_handlers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_event(**kwargs: str) -> ESLEvent:
    event = ESLEvent()
    event.update(kwargs)
    return event


# ---------------------------------------------------------------------------
# ChannelRoutingStrategy
# ---------------------------------------------------------------------------


async def test_channel_routing_match_returns_handlers_and_stops():
    uuid = "test-uuid-123"
    registry = {f"{uuid}:CHANNEL_STATE": [MagicMock()]}
    strategy = ChannelRoutingStrategy(registry)
    event = make_event(**{"Unique-ID": uuid, "Event-Name": "CHANNEL_STATE"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == registry[f"{uuid}:CHANNEL_STATE"]
    assert should_stop is True


async def test_channel_routing_miss_returns_empty_and_false():
    strategy = ChannelRoutingStrategy({})
    event = make_event(**{"Unique-ID": "unknown-uuid", "Event-Name": "CHANNEL_STATE"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


async def test_channel_routing_custom_event_uses_subclass():
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


async def test_channel_routing_no_uuid_returns_empty():
    strategy = ChannelRoutingStrategy({"x:HEARTBEAT": [MagicMock()]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


# ---------------------------------------------------------------------------
# GlobalRoutingStrategy
# ---------------------------------------------------------------------------


async def test_global_routing_match_by_event_name():
    handler = MagicMock()
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [handler]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, should_stop = await strategy.route(event)

    assert handler in handlers
    assert should_stop is False


async def test_global_routing_wildcard_matches_any_event():
    wildcard = MagicMock()
    strategy = GlobalRoutingStrategy({"*": [wildcard]})
    event = make_event(**{"Event-Name": "CHANNEL_CREATE"})

    handlers, should_stop = await strategy.route(event)

    assert wildcard in handlers
    assert should_stop is False


async def test_global_routing_specific_and_wildcard_combined():
    specific = MagicMock()
    wildcard = MagicMock()
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [specific], "*": [wildcard]})
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    handlers, _ = await strategy.route(event)

    assert specific in handlers
    assert wildcard in handlers


async def test_global_routing_miss_returns_empty():
    strategy = GlobalRoutingStrategy({"HEARTBEAT": [MagicMock()]})
    event = make_event(**{"Event-Name": "CHANNEL_HANGUP"})

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


async def test_global_routing_no_event_name_returns_empty():
    strategy = GlobalRoutingStrategy({"*": [MagicMock()]})
    event = ESLEvent()

    handlers, should_stop = await strategy.route(event)

    assert handlers == []
    assert should_stop is False


# ---------------------------------------------------------------------------
# CompositeRoutingStrategy
# ---------------------------------------------------------------------------


async def test_composite_stops_at_first_strategy_with_handlers():
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


async def test_composite_falls_through_to_next_strategy():
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


async def test_composite_no_match_returns_empty():
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


async def test_composite_propagates_should_stop_true():
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


async def test_dispatch_creates_tasks_in_set():
    done = asyncio.Event()

    async def handler(event: ESLEvent) -> None:
        done.set()

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([handler], event, task_set)

    # At least one task should be in the set immediately after dispatch
    assert len(task_set) == 1

    await asyncio.wait_for(done.wait(), timeout=5)


async def test_dispatch_task_removed_from_set_after_completion():
    done = asyncio.Event()

    async def handler(event: ESLEvent) -> None:
        done.set()

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([handler], event, task_set)
    await asyncio.wait_for(done.wait(), timeout=5)
    # Give the done callback a chance to run
    await asyncio.sleep(0)

    assert len(task_set) == 0


async def test_dispatch_exception_in_handler_is_logged_not_propagated():
    from unittest.mock import patch

    async def bad_handler(event: ESLEvent) -> None:
        raise ValueError("handler exploded")

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    with patch("genesis.protocol.routing.dispatcher.logger") as mock_log:
        dispatch_to_handlers([bad_handler], event, task_set)
        tasks = list(task_set)
        for task in tasks:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except Exception:
                pass
        await asyncio.sleep(0)

    error_calls = mock_log.error.call_args_list
    assert any("handler exploded" in str(call) for call in error_calls)


async def test_dispatch_sync_handler_via_to_thread():
    results = []

    def sync_handler(event: ESLEvent) -> None:
        results.append(event.get("Event-Name"))

    task_set: set[Task[Any]] = set()
    event = make_event(**{"Event-Name": "HEARTBEAT"})

    dispatch_to_handlers([sync_handler], event, task_set)
    tasks = list(task_set)
    await asyncio.gather(*tasks)

    assert results == ["HEARTBEAT"]


async def test_dispatch_no_task_set_does_not_raise():
    """dispatch_to_handlers must work without a task_set (backwards compat)."""
    done = asyncio.Event()

    async def handler(event: ESLEvent) -> None:
        done.set()

    event = make_event(**{"Event-Name": "HEARTBEAT"})
    dispatch_to_handlers([handler], event)
    await asyncio.wait_for(done.wait(), timeout=5)
