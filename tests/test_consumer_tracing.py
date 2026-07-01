"""Tests for Consumer start/stop OpenTelemetry instrumentation."""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis import Consumer


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


async def _wait_for_span(
    exporter: InMemorySpanExporter, name: str, timeout: float = 5.0
):
    """Event-based poll (no sleep) for a finished span by name."""
    start = asyncio.get_event_loop().time()
    while True:
        if any(s.name == name for s in exporter.get_finished_spans()):
            return
        if asyncio.get_event_loop().time() - start >= timeout:
            raise TimeoutError(f"span '{name}' not seen within {timeout}s")
        future = asyncio.Future()
        asyncio.get_event_loop().call_soon(future.set_result, None)
        await future


async def test_consumer_start_and_stop_spans(freeswitch, memory_exporter):
    """Consumer.start emits consumer.start (setup phase) and stop emits consumer.stop."""
    consumer = Consumer(*freeswitch.address)

    start_task = asyncio.create_task(consumer.start())
    # Wait for the setup-phase span to finalize (before the blocking wait loop).
    await _wait_for_span(memory_exporter, "consumer.start", timeout=5.0)

    await consumer.stop()
    try:
        await asyncio.wait_for(start_task, timeout=5.0)
    except (asyncio.TimeoutError, Exception):
        start_task.cancel()

    spans = {s.name for s in memory_exporter.get_finished_spans()}
    assert "consumer.start" in spans
    assert "consumer.stop" in spans

    start_span = next(
        s for s in memory_exporter.get_finished_spans() if s.name == "consumer.start"
    )
    assert start_span.attributes["consumer.host"] == freeswitch.address[0]
    assert "consumer.port" in start_span.attributes
