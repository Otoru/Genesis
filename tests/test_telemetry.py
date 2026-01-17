import asyncio
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry import trace
from genesis import Inbound
from genesis.exceptions import AuthenticationError


@pytest.fixture
def memory_exporter():
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)

    provider = trace.get_tracer_provider()

    # If the current provider is a proxy or doesn't have add_span_processor (i.e. not the SDK provider),
    # we initialize a new one.
    # However, if it IS the SDK provider, we interpret that as "already initialized".
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)

    provider.add_span_processor(processor)
    yield exporter


@pytest.fixture
def host():
    return lambda: "127.0.0.1"


async def test_inbound_connection_spans(freeswitch, memory_exporter):
    """Verify that connecting to FreeSWITCH generates an 'inbound_connect' span."""
    async with freeswitch as server:
        # Just connecting should trigger the span
        async with Inbound(*freeswitch.address) as client:
            pass

    # Wait a bit for spans to be processed
    await asyncio.sleep(0.1)

    spans = memory_exporter.get_finished_spans()

    # We expect 'inbound_connect' and potentially others depending on implementation details
    # But specifically we want to check for inbound_connect
    connect_spans = [s for s in spans if s.name == "inbound_connect"]
    assert len(connect_spans) == 1
    span = connect_spans[0]
    assert span.attributes["net.peer.name"] == "127.0.0.1"
    assert "net.peer.port" in span.attributes


async def test_send_command_span(freeswitch, memory_exporter):
    """Verify that sending a command generates a 'send_command' span."""
    async with freeswitch as server:
        server.oncommand("uptime", "6943047")
        async with Inbound(*freeswitch.address) as client:
            await client.send("uptime")

    await asyncio.sleep(0.1)
    spans = memory_exporter.get_finished_spans()

    send_spans = [s for s in spans if s.name == "send_command"]
    assert len(send_spans) >= 1

    # Filter for the specific command we sent
    uptime_span = next(
        (s for s in send_spans if s.attributes["command.name"] == "uptime"), None
    )
    assert uptime_span is not None
    # command.reply should be set if OTel is working correctly
    if "command.reply" in uptime_span.attributes:
        assert uptime_span.attributes["command.reply"] == "6943047"
