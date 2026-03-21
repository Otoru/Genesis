"""Tests for genesis loop utilities (uvloop support)."""

import pytest

from genesis.loop import use_uvloop


def test_use_uvloop_returns_bool() -> None:
    """use_uvloop() returns True if uvloop was set, False otherwise."""
    result = use_uvloop()
    assert isinstance(result, bool)
