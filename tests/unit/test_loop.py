"""Tests for genesis loop utilities (uvloop support)."""

import asyncio

from genesis.loop import use_uvloop


def test_use_uvloop_returns_bool() -> None:
    """use_uvloop() returns True if uvloop was set, False otherwise."""
    previous = asyncio.get_event_loop_policy()
    try:
        result = use_uvloop()
        assert isinstance(result, bool)
    finally:
        asyncio.set_event_loop_policy(previous)
