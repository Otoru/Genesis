"""
Metrics definitions for Protocol operations.

This module centralizes all OpenTelemetry metrics used by the Protocol
and related components (Channel, Session, Inbound, Outbound, etc.).

Centralization avoids duplicated instrument definitions (which both trip
static analysis and produce OTel SDK warnings when the same metric name is
created with different descriptions in multiple modules).
"""

import weakref
from typing import Any, Iterable

from opentelemetry import trace, metrics
from opentelemetry.metrics import Observation

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# ---------------------------------------------------------------------------
# Command metrics
# ---------------------------------------------------------------------------
commands_sent_counter = meter.create_counter(
    "genesis.commands.sent",
    description="Number of ESL commands sent",
    unit="1",
)

events_received_counter = meter.create_counter(
    "genesis.events.received",
    description="Number of ESL events received",
    unit="1",
)

command_duration_histogram = meter.create_histogram(
    "genesis.commands.duration",
    description="Duration of ESL commands execution",
    unit="s",
)

command_errors_counter = meter.create_counter(
    "genesis.commands.errors",
    description="Number of failed ESL commands",
    unit="1",
)

# ---------------------------------------------------------------------------
# Channel operation metrics
# ---------------------------------------------------------------------------
channel_operations_counter = meter.create_counter(
    "genesis.channel.operations",
    description="Number of channel operations",
    unit="1",
)

channel_operation_duration = meter.create_histogram(
    "genesis.channel.operation.duration",
    description="Duration of channel operations",
    unit="s",
)

hangup_causes_counter = meter.create_counter(
    "genesis.channel.hangup.causes",
    description="Hangup causes",
    unit="1",
)

bridge_operations_counter = meter.create_counter(
    "genesis.channel.bridge.operations",
    description="Bridge operations",
    unit="1",
)

dtmf_received_counter = meter.create_counter(
    "genesis.channel.dtmf.received",
    description="DTMF digits received",
    unit="1",
)

call_duration_histogram = meter.create_histogram(
    "genesis.call.duration",
    description="Total call duration from creation to hangup",
    unit="s",
)

timeout_counter = meter.create_counter(
    "genesis.timeouts",
    description="Number of timeouts",
    unit="1",
)

# ---------------------------------------------------------------------------
# Routing metrics (for O(1) event routing)
# ---------------------------------------------------------------------------
channel_routing_counter = meter.create_counter(
    "genesis.channel.routing.hits",
    description="Number of O(1) channel routing hits",
    unit="1",
)

global_routing_counter = meter.create_counter(
    "genesis.channel.routing.fallback",
    description="Number of fallback to O(N) global routing",
    unit="1",
)

# ---------------------------------------------------------------------------
# Connection metrics (shared by Inbound and Outbound)
# ---------------------------------------------------------------------------
connections_active_counter = meter.create_up_down_counter(
    "genesis.connections.active",
    description="Number of active connections",
    unit="1",
)

connection_errors_counter = meter.create_counter(
    "genesis.connections.errors",
    description="Number of connection errors",
    unit="1",
)

# ---------------------------------------------------------------------------
# New ESL lifecycle / routing correlation metrics
# ---------------------------------------------------------------------------
# Cardinality rule: metric attributes NEVER carry UUIDs; only low-cardinality
# enums/labels (channel.state, direction, hangup.cause, application.name, ...).
# UUIDs go on spans only.
calls_active_counter = meter.create_up_down_counter(
    "genesis.calls.active",
    description="Number of active calls by state and direction",
    unit="1",
)

channel_bridge_events_counter = meter.create_counter(
    "genesis.channel.bridge.events",
    description="ESL CHANNEL_BRIDGE/UNBRIDGE events (authoritative bridge state)",
    unit="1",
)

channel_transfers_counter = meter.create_counter(
    "genesis.channel.transfers",
    description="Call transfers observed via sofia::transferor/transferee",
    unit="1",
)

channel_codec_changes_counter = meter.create_counter(
    "genesis.channel.codec.changes",
    description="Codec renegotiations observed via CODEC events",
    unit="1",
)

dialplan_applications_counter = meter.create_counter(
    "genesis.dialplan.applications",
    description="Dialplan applications executed (CHANNEL_EXECUTE[_COMPLETE])",
    unit="1",
)

hangup_q850_counter = meter.create_counter(
    "genesis.channel.hangup.causes.q850",
    description="Hangup causes by Q.850 code",
    unit="1",
)

event_processing_duration = meter.create_histogram(
    "genesis.event.processing.duration",
    description="Duration of event dispatch (processors + routing)",
    unit="s",
)

events_without_sip_call_id_counter = meter.create_counter(
    "genesis.events.without_sip_call_id",
    description="Channel events lacking variable_sip_call_id (correlation gap)",
    unit="1",
)

# ---------------------------------------------------------------------------
# Session / consumer / load balancer metrics
# ---------------------------------------------------------------------------
session_commands_counter = meter.create_counter(
    "genesis.session.commands",
    description="Session sendmsg commands by application",
    unit="1",
)

session_command_duration = meter.create_histogram(
    "genesis.session.command.duration",
    description="Duration of session sendmsg commands",
    unit="s",
)

consumer_handlers_counter = meter.create_counter(
    "genesis.consumer.handlers",
    description="Consumer handler invocations by event and match result",
    unit="1",
)

loadbalancer_selections_counter = meter.create_counter(
    "genesis.loadbalancer.selections",
    description="Load balancer selections by backend and result",
    unit="1",
)

loadbalancer_errors_counter = meter.create_counter(
    "genesis.loadbalancer.errors",
    description="Load balancer errors by error type",
    unit="1",
)

# ---------------------------------------------------------------------------
# Observable gauges for queue depth (backpressure visibility)
# ---------------------------------------------------------------------------
# Protocols register themselves (weakly) so the gauge callbacks can sum the
# pending events/commands across all live instances without holding them alive.
_protocol_registry: "weakref.WeakSet[Any]" = weakref.WeakSet()


def register_protocol(protocol: Any) -> None:
    """Register a Protocol instance so its queue depths feed the gauges."""
    _protocol_registry.add(protocol)


def _commands_queue_depth(_options: Any) -> Iterable[Observation]:
    total = 0
    for proto in tuple(_protocol_registry):
        try:
            total += proto.commands.qsize()
        except Exception:
            pass
    yield Observation(total, {})


def _events_queue_depth(_options: Any) -> Iterable[Observation]:
    total = 0
    for proto in tuple(_protocol_registry):
        try:
            total += proto.events.qsize()
        except Exception:
            pass
    yield Observation(total, {})


commands_queue_depth_gauge = meter.create_observable_gauge(
    "genesis.commands.queue.depth",
    callbacks=[_commands_queue_depth],
    description="Depth of the pending command reply queue",
    unit="1",
)

events_queue_depth_gauge = meter.create_observable_gauge(
    "genesis.events.queue.depth",
    callbacks=[_events_queue_depth],
    description="Depth of the pending event queue",
    unit="1",
)


def safe_add(counter: Any, *args: Any, **kwargs: Any) -> None:
    """Add to a counter, swallowing OTel/metrics errors (best-effort)."""
    try:
        getattr(counter, "add")(*args, **kwargs)
    except Exception:
        pass


def safe_record(histogram: Any, *args: Any, **kwargs: Any) -> None:
    """Record on a histogram, swallowing OTel/metrics errors (best-effort)."""
    try:
        getattr(histogram, "record")(*args, **kwargs)
    except Exception:
        pass


# Re-export for callers that import a batch of instruments (kept alphabetical).
__all__ = [
    "tracer",
    "meter",
    "commands_sent_counter",
    "events_received_counter",
    "command_duration_histogram",
    "command_errors_counter",
    "channel_operations_counter",
    "channel_operation_duration",
    "hangup_causes_counter",
    "bridge_operations_counter",
    "dtmf_received_counter",
    "call_duration_histogram",
    "timeout_counter",
    "channel_routing_counter",
    "global_routing_counter",
    "connections_active_counter",
    "connection_errors_counter",
    "calls_active_counter",
    "channel_bridge_events_counter",
    "channel_transfers_counter",
    "channel_codec_changes_counter",
    "dialplan_applications_counter",
    "hangup_q850_counter",
    "event_processing_duration",
    "events_without_sip_call_id_counter",
    "session_commands_counter",
    "session_command_duration",
    "consumer_handlers_counter",
    "loadbalancer_selections_counter",
    "loadbalancer_errors_counter",
    "commands_queue_depth_gauge",
    "events_queue_depth_gauge",
    "register_protocol",
    "safe_add",
    "safe_record",
]
