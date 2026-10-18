"""Lifecycle and CUSTOM subclass spans from parsed event text. No TCP."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any, Callable
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import Span

from genesis.protocol.base import Protocol
from genesis.protocol.lifecycle import (
    channel_lifecycle_processor,
    custom_subclass_processor,
    safe_add,
)
from genesis.protocol.parser import ESLEvent, parse_headers
from tests.references.synthetic.telemetry_payloads import (
    SIP_CALL_ID,
    UUID_A,
    UUID_B,
    call_update,
    callcenter_info,
    channel_bridge,
    channel_create,
    channel_create_no_sip,
    channel_destroy,
    channel_execute,
    channel_execute_complete,
    channel_hangup_complete,
    channel_unbridge,
    codec,
    conference_maintenance,
    heartbeat,
    sofia_transferee,
    sofia_transferor,
    valet_info,
)

_UUIDS = frozenset(
    {
        "d0b1da34-a727-11e4-9728-6f83a2e5e50a",
        UUID_A,
        UUID_B,
        "app-uuid-1",
        "member-uuid-1",
        SIP_CALL_ID,
    }
)


class _HandlerProtocol(Protocol):
    async def start(self) -> None:
        self.is_connected = True


@pytest.fixture
def memory_exporter() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider: Any = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(processor)
    yield exporter


def _event(payload: str) -> ESLEvent:
    return parse_headers(payload)


def _span(exporter: InMemorySpanExporter, name: str) -> Span:
    spans = [span for span in exporter.get_finished_spans() if span.name == name]
    assert spans, "span '%s' not emitted; got %s" % (
        name,
        [span.name for span in exporter.get_finished_spans()],
    )
    return spans[-1]


def exporter_names(exporter: InMemorySpanExporter) -> list[str]:
    return [span.name for span in exporter.get_finished_spans()]


async def test_channel_create_emits_span_and_sip_call_id(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_create)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.create")
    assert "sip.call_id" in span.attributes
    assert span.attributes["sip.call_id"]
    assert span.attributes["channel.uuid"] == "d0b1da34-a727-11e4-9728-6f83a2e5e50a"
    assert span.attributes["channel.destination_number"] == "101"


async def test_channel_bridge_carries_cross_leg_uuids(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_bridge)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.bridge")
    assert span.attributes["bridge.a_uuid"] == UUID_A
    assert span.attributes["bridge.b_uuid"] == UUID_B
    assert span.attributes["sip.call_id"] == SIP_CALL_ID
    events = [event for event in span.events if event.name == "bridge.established"]
    assert events, "bridge.established event not emitted"


async def test_channel_unbridge_emits_torn_down_event(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_unbridge)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.unbridge")
    assert span.attributes["sip.call_id"] == SIP_CALL_ID
    assert [event for event in span.events if event.name == "bridge.torn_down"]


async def test_hangup_complete_records_q850(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_hangup_complete)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]

    span = _span(memory_exporter, "freeswitch.channel.hangup_complete")
    assert span.attributes["hangup.cause.q850"] == "16"
    assert span.attributes["sip.call_id"] == SIP_CALL_ID
    assert [event for event in span.events if event.name == "call.finalized"]


async def test_channel_destroy_emits_span(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_destroy)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.destroy")
    assert span.attributes["sip.call_id"] == SIP_CALL_ID


async def test_execute_and_complete_spans(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(channel_execute)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.execute")
    assert span.attributes["application.name"] == "playback"
    assert span.attributes["application.uuid"] == "app-uuid-1"

    event = _event(channel_execute_complete)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.execute_complete")
    assert span.attributes["application.name"] == "playback"


async def test_codec_span(memory_exporter: InMemorySpanExporter) -> None:
    event = _event(codec)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.codec")
    assert span.attributes["channel.read_codec.name"] == "opus"
    assert span.attributes["sip.call_id"] == SIP_CALL_ID


async def test_call_update_span(memory_exporter: InMemorySpanExporter) -> None:
    event = _event(call_update)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.call.update")
    assert span.attributes["sip.call_id"] == SIP_CALL_ID


async def test_sofia_transfer_blind_and_attended(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(sofia_transferor)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.sofia.transfer")
    assert span.attributes["transfer.role"] == "transferor"
    assert span.attributes["transfer.type"] == "blind"

    event = _event(sofia_transferee)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.sofia.transfer")
    assert span.attributes["transfer.role"] == "transferee"
    assert span.attributes["transfer.type"] == "attended"


async def test_callcenter_info_span(memory_exporter: InMemorySpanExporter) -> None:
    event = _event(callcenter_info)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.callcenter.info")
    assert span.attributes["cc.queue"] == "sales"
    assert span.attributes["cc.action"] == "agent-state-change"


async def test_conference_maintenance_span(
    memory_exporter: InMemorySpanExporter,
) -> None:
    event = _event(conference_maintenance)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.conference.maintenance")
    assert span.attributes["conference.name"] == "3000"
    assert span.attributes["conference.action"] == "add-member"


async def test_valet_info_span(memory_exporter: InMemorySpanExporter) -> None:
    event = _event(valet_info)
    custom_subclass_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.valet.info")
    assert span.attributes["valet.lot"] == "default"
    assert span.attributes["bridge.to_uuid"] == UUID_B


async def test_no_sip_call_id_event_still_emits_span(
    memory_exporter: InMemorySpanExporter,
) -> None:
    """A channel event without the correlation key still traces; the gap is
    counted by the events_without_sip_call_id metric (no crash, no missing span)."""
    event = _event(channel_create_no_sip)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    span = _span(memory_exporter, "freeswitch.channel.create")
    assert "sip.call_id" not in span.attributes


async def test_non_lifecycle_event_is_noop(
    memory_exporter: InMemorySpanExporter,
) -> None:
    """A HEARTBEAT must not produce a lifecycle span."""
    event = _event(heartbeat)
    channel_lifecycle_processor(None, event)  # type: ignore[arg-type]
    spans = exporter_names(memory_exporter)
    assert not any(name.startswith("freeswitch.channel.") for name in spans)


def test_lifecycle_metric_labels_omit_uuids(
    memory_exporter: InMemorySpanExporter,
) -> None:
    seen: list[dict[str, str]] = []

    def spy(counter: object, *args: object, **kwargs: object) -> None:
        attributes = kwargs.get("attributes")
        if isinstance(attributes, dict):
            seen.append({str(key): str(value) for key, value in attributes.items()})
        safe_add(counter, *args, **kwargs)

    payloads: list[tuple[Callable[..., None], str]] = [
        (channel_lifecycle_processor, channel_create),
        (channel_lifecycle_processor, channel_bridge),
        (channel_lifecycle_processor, channel_execute),
        (channel_lifecycle_processor, channel_hangup_complete),
        (channel_lifecycle_processor, codec),
        (channel_lifecycle_processor, channel_create_no_sip),
        (custom_subclass_processor, valet_info),
    ]
    with patch("genesis.protocol.lifecycle.safe_add", spy):
        for processor, payload in payloads:
            processor(None, _event(payload))  # type: ignore[arg-type]

    creates = [
        span
        for span in memory_exporter.get_finished_spans()
        if span.name == "freeswitch.channel.create"
    ]
    correlated = [span for span in creates if "sip.call_id" in span.attributes]
    assert correlated
    assert correlated[0].attributes["channel.uuid"] == (
        "d0b1da34-a727-11e4-9728-6f83a2e5e50a"
    )
    assert any("sip.call_id" not in span.attributes for span in creates)
    assert {} in seen
    bridge = _span(memory_exporter, "freeswitch.channel.bridge")
    assert bridge.attributes["bridge.a_uuid"] == UUID_A
    assert bridge.attributes["bridge.b_uuid"] == UUID_B
    assert seen, "lifecycle processors recorded no metric attributes"
    for attributes in seen:
        for key, value in attributes.items():
            assert "uuid" not in key.lower()
            assert value not in _UUIDS


async def test_user_handler_still_receives_lifecycle_event(
    memory_exporter: InMemorySpanExporter,
) -> None:
    protocol = _HandlerProtocol()
    received: list[str] = []

    async def handler(event: ESLEvent) -> None:
        name = event.get("Event-Name")
        received.append(name if isinstance(name, str) else "")

    protocol.on("CHANNEL_CREATE", handler)
    await protocol._process_one_event(_event(channel_create))
    assert protocol.handler_tasks
    done, pending = await asyncio.wait(list(protocol.handler_tasks), timeout=1)
    assert not pending
    for task in done:
        assert task.exception() is None
    assert received == ["CHANNEL_CREATE"]
    span = _span(memory_exporter, "freeswitch.channel.create")
    assert "sip.call_id" in span.attributes
    assert span.attributes["channel.uuid"] == "d0b1da34-a727-11e4-9728-6f83a2e5e50a"
