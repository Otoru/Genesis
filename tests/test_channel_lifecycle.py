"""Tests for the ESL lifecycle / CUSTOM subclass telemetry processors.

These processors emit ``freeswitch.channel.*`` and ``freeswitch.sofia.*`` /
``freeswitch.callcenter.*`` / ``freeswitch.conference.*`` / ``freeswitch.valet.*``
spans. The key contract under test is **cross-system correlation**: every channel
span must carry ``sip.call_id`` (= ``variable_sip_call_id``, the standard SIP
Call-ID) so another system's view of the same call can be joined to it at the
observability backend.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis.protocol.lifecycle import (
    channel_lifecycle_processor,
    custom_subclass_processor,
)
from genesis.protocol.parser import parse_headers
from tests import payloads


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


def _event(payload: str):
    return parse_headers(payload)


def _span(exporter: InMemorySpanExporter, name: str):
    spans = [s for s in exporter.get_finished_spans() if s.name == name]
    assert (
        spans
    ), f"span '{name}' not emitted; got {[s.name for s in exporter.get_finished_spans()]}"
    return spans[-1]


async def test_channel_create_emits_span_and_sip_call_id(memory_exporter):
    event = _event(payloads.channel_create)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.create")
    # Correlation contract: sip.call_id must be present on the span.
    assert "sip.call_id" in span.attributes
    assert span.attributes["sip.call_id"]
    assert span.attributes["channel.uuid"] == "d0b1da34-a727-11e4-9728-6f83a2e5e50a"
    assert span.attributes["channel.destination_number"] == "101"


async def test_channel_bridge_carries_cross_leg_uuids(memory_exporter):
    event = _event(payloads.channel_bridge)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.bridge")
    assert span.attributes["bridge.a_uuid"] == payloads.UUID_A
    assert span.attributes["bridge.b_uuid"] == payloads.UUID_B
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID
    events = [e for e in span.events if e.name == "bridge.established"]
    assert events, "bridge.established event not emitted"


async def test_channel_unbridge_emits_torn_down_event(memory_exporter):
    event = _event(payloads.channel_unbridge)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.unbridge")
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID
    assert [e for e in span.events if e.name == "bridge.torn_down"]


async def test_hangup_complete_records_q850(memory_exporter):
    event = _event(payloads.channel_hangup_complete)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.hangup_complete")
    assert span.attributes["hangup.cause.q850"] == "16"
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID
    assert [e for e in span.events if e.name == "call.finalized"]


async def test_channel_destroy_emits_span(memory_exporter):
    event = _event(payloads.channel_destroy)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.destroy")
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID


async def test_execute_and_complete_spans(memory_exporter):
    event = _event(payloads.channel_execute)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.execute")
    assert span.attributes["application.name"] == "playback"
    assert span.attributes["application.uuid"] == "app-uuid-1"

    event = _event(payloads.channel_execute_complete)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.execute_complete")
    assert span.attributes["application.name"] == "playback"


async def test_codec_span(memory_exporter):
    event = _event(payloads.codec)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.codec")
    assert span.attributes["channel.read_codec.name"] == "opus"
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID


async def test_call_update_span(memory_exporter):
    event = _event(payloads.call_update)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.call.update")
    assert span.attributes["sip.call_id"] == payloads.SIP_CALL_ID


async def test_sofia_transfer_blind_and_attended(memory_exporter):
    event = _event(payloads.sofia_transferor)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.sofia.transfer")
    assert span.attributes["transfer.role"] == "transferor"
    assert span.attributes["transfer.type"] == "blind"

    event = _event(payloads.sofia_transferee)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.sofia.transfer")
    assert span.attributes["transfer.role"] == "transferee"
    assert span.attributes["transfer.type"] == "attended"


async def test_callcenter_info_span(memory_exporter):
    event = _event(payloads.callcenter_info)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.callcenter.info")
    assert span.attributes["cc.queue"] == "sales"
    assert span.attributes["cc.action"] == "agent-state-change"


async def test_conference_maintenance_span(memory_exporter):
    event = _event(payloads.conference_maintenance)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.conference.maintenance")
    assert span.attributes["conference.name"] == "3000"
    assert span.attributes["conference.action"] == "add-member"


async def test_valet_info_span(memory_exporter):
    event = _event(payloads.valet_info)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.valet.info")
    assert span.attributes["valet.lot"] == "default"
    assert span.attributes["bridge.to_uuid"] == payloads.UUID_B


async def test_no_sip_call_id_event_still_emits_span(memory_exporter):
    """A channel event without the correlation key still traces; the gap is
    counted by the events_without_sip_call_id metric (no crash, no missing span)."""
    event = _event(payloads.channel_create_no_sip)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.create")
    assert "sip.call_id" not in span.attributes


async def test_non_lifecycle_event_is_noop(memory_exporter):
    """A HEARTBEAT must not produce a lifecycle span."""
    event = _event(payloads.heartbeat)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    spans = exporter_names(memory_exporter)
    assert not any(name.startswith("freeswitch.channel.") for name in spans)


def exporter_names(exporter: InMemorySpanExporter):
    return [s.name for s in exporter.get_finished_spans()]
