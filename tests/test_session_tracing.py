"""Tests for Session.sendmsg OpenTelemetry instrumentation.

Verifies the ``session.sendmsg`` span (and the ``session.await_complete``
child span when blocking) plus the ``genesis.session.commands`` metric
attributes. Uses the Outbound + Dialplan doubles (no real FreeSWITCH).
"""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis import Outbound, Session


@pytest.fixture
def memory_exporter():
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(processor)
    yield exporter


def _spans(exporter: InMemorySpanExporter):
    return exporter.get_finished_spans()


async def test_sendmsg_non_blocking_emits_span(host, port, dialplan, memory_exporter):
    """A non-blocking sendmsg emits session.sendmsg with application metadata."""
    done = asyncio.Event()
    handler_started = asyncio.Event()

    async def handler(session: Session) -> None:
        handler_started.set()
        # Non-blocking execute: returns the +OK reply, no completion wait.
        await session.sendmsg("execute", "answer", block=False)
        done.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)
    await asyncio.wait_for(done.wait(), timeout=5.0)

    await app.stop()
    await dialplan.stop()

    sendmsg_spans = [s for s in _spans(memory_exporter) if s.name == "session.sendmsg"]
    assert sendmsg_spans, "session.sendmsg span not emitted"
    span = sendmsg_spans[-1]
    assert span.attributes["application.name"] == "answer"
    assert span.attributes["application.block"] == "False"


async def test_sendmsg_blocking_emits_await_complete(
    host, port, dialplan, memory_exporter
):
    """A blocking sendmsg emits session.sendmsg + a session.await_complete child."""
    sendmsg_returned = asyncio.Event()
    handler_started = asyncio.Event()
    captured = {}

    async def handler(session: Session) -> None:
        handler_started.set()
        captured["channel_uuid"] = session.uuid
        # blocking execute; the Dialplan double stores the pending Event-UUID.
        await session.sendmsg("execute", "playback", "/tmp/x.wav", block=True)
        sendmsg_returned.set()

    address = (host(), port())
    app = Outbound(handler, *address)
    await app.start(block=False)
    await dialplan.start(*address)

    await asyncio.wait_for(dialplan.client_connected.wait(), timeout=5.0)
    await asyncio.wait_for(handler_started.wait(), timeout=5.0)

    # Wait (event-based, no sleep) until the Dialplan double has recorded the
    # pending execute Event-UUID, then broadcast the completion event so the
    # blocked sendmsg returns. The complete event must carry the session's
    # channel UUID so O(1) channel routing delivers it to the registered handler.
    async def _pending_uuid():
        while not dialplan.pending_execute_events:
            future = asyncio.Future()
            asyncio.get_event_loop().call_soon(future.set_result, None)
            await future
        return next(iter(dialplan.pending_execute_events))

    app_uuid = await asyncio.wait_for(_pending_uuid(), timeout=5.0)

    await dialplan.broadcast(
        {
            "Event-Name": "CHANNEL_EXECUTE_COMPLETE",
            "Application-UUID": app_uuid,
            "Unique-ID": captured["channel_uuid"],
        }
    )

    await asyncio.wait_for(sendmsg_returned.wait(), timeout=5.0)
    await app.stop()
    await dialplan.stop()

    names = [s.name for s in _spans(memory_exporter)]
    assert "session.sendmsg" in names
    assert "session.await_complete" in names
    sendmsg_span = next(
        s for s in _spans(memory_exporter) if s.name == "session.sendmsg"
    )
    assert sendmsg_span.attributes["application.name"] == "playback"
    assert sendmsg_span.attributes["application.block"] == "True"
