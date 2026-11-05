"""Tests for genesis loop utilities (uvloop support)."""

import asyncio
import sys
import warnings

import pytest

from genesis.loop import new_event_loop, use_uvloop


def test_new_event_loop_uses_uvloop_when_installed() -> None:
    uvloop = pytest.importorskip("uvloop")
    loop = new_event_loop()
    try:
        assert isinstance(loop, uvloop.Loop)
    finally:
        loop.close()


def test_new_event_loop_falls_back_without_uvloop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "uvloop", None)
    loop = new_event_loop()
    try:
        assert isinstance(loop, asyncio.BaseEventLoop)
    finally:
        loop.close()


def test_new_event_loop_runs_a_coroutine() -> None:
    async def answer() -> int:
        return 42

    with asyncio.Runner(loop_factory=new_event_loop) as runner:
        assert runner.run(answer()) == 42


def test_use_uvloop_is_deprecated() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        previous = asyncio.get_event_loop_policy()
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = use_uvloop()
        assert isinstance(result, bool)
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "use_uvloop" in str(w.message)
            and w.filename == __file__
            for w in caught
        )
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            asyncio.set_event_loop_policy(previous)
