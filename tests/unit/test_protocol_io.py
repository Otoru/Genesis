"""Tests for Protocol base class private I/O helpers."""

import asyncio
from asyncio import StreamReader
from unittest.mock import AsyncMock, patch

import pytest

from genesis.protocol.base import Protocol


class _ConcreteProtocol(Protocol):
    """Minimal concrete Protocol for testing private helpers."""

    async def start(self) -> None:  # type: ignore[override]
        pass


def _make_protocol(reader: StreamReader | None = None) -> _ConcreteProtocol:
    proto = _ConcreteProtocol()
    proto.reader = reader
    proto.is_connected = True
    return proto


async def test_read_header_block_returns_block():
    """_read_header_block returns the accumulated header string on \\n\\n."""
    reader = StreamReader()
    reader.feed_data(b"Content-Type: command/reply\n\n")
    proto = _make_protocol(reader)
    block = await proto._read_header_block()
    assert block == "Content-Type: command/reply\n\n"
    assert proto.is_connected is True


async def test_read_header_block_eof_sets_disconnected():
    """_read_header_block returns None and sets is_connected=False on EOF."""
    reader = StreamReader()
    reader.feed_eof()
    proto = _make_protocol(reader)
    result = await proto._read_header_block()
    assert result is None
    assert proto.is_connected is False


async def test_read_header_block_exception_sets_disconnected():
    """_read_header_block returns None and sets is_connected=False on read error."""
    reader = AsyncMock(spec=StreamReader)
    reader.readline.side_effect = OSError("network error")
    proto = _make_protocol(reader)
    result = await proto._read_header_block()
    assert result is None
    assert proto.is_connected is False


async def test_read_body_bytes_returns_bytes():
    """_read_body_bytes returns the exact bytes requested."""
    reader = StreamReader()
    reader.feed_data(b"hello world")
    proto = _make_protocol(reader)
    result = await proto._read_body_bytes(5)
    assert result == b"hello"
    assert proto.is_connected is True


async def test_read_body_bytes_exception_sets_disconnected():
    """_read_body_bytes returns None and sets is_connected=False on read error."""
    reader = AsyncMock(spec=StreamReader)
    reader.readexactly.side_effect = asyncio.IncompleteReadError(b"", 10)
    proto = _make_protocol(reader)
    result = await proto._read_body_bytes(10)
    assert result is None
    assert proto.is_connected is False
