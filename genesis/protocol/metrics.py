"""
Metrics definitions for Protocol operations.

This module centralizes all OpenTelemetry metrics used by the Protocol
and related components (Channel, Session, etc.).
"""

from opentelemetry import trace, metrics

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Command metrics
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

# Channel operation metrics
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

# Routing metrics (for O(1) event routing)
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
