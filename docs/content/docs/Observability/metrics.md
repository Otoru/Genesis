---
title: Metrics
weight: 40
---

Genesis exposes metrics via OpenTelemetry that can be scraped by Prometheus.

## Available Metrics

Genesis exposes the following metrics via OpenTelemetry:

**Command Metrics:**
- **`genesis_commands_sent_total`** (Counter)
  - Description: Number of ESL commands sent
  - Attributes: `command`

- **`genesis_commands_duration_seconds`** (Histogram)
  - Description: Command execution duration (RTT)
  - Attributes: `command`

- **`genesis_commands_errors_total`** (Counter)
  - Description: Number of failed ESL commands
  - Attributes: `command`, `error`

**Event Metrics:**
- **`genesis_events_received_total`** (Counter)
  - Description: Number of ESL events received
  - Attributes: `event_name`, `event_subclass`, `direction`, `channel_state`, `answer_state`, `hangup_cause`

**Connection Metrics:**
- **`genesis_connections_active`** (Gauge)
  - Description: Number of active connections
  - Attributes: `type` (inbound/outbound)

- **`genesis_connections_errors_total`** (Counter)
  - Description: Number of connection errors
  - Attributes: `type`, `error`

**Channel Operation Metrics:**
- **`genesis_channel_operations_total`** (Counter)
  - Description: Number of channel operations
  - Attributes: `operation` (answer, hangup, bridge, playback, say, etc.), `success`, `error`

- **`genesis_channel_operation_duration_seconds`** (Histogram)
  - Description: Duration of channel operations
  - Attributes: `operation`

- **`genesis_channel_hangup_causes_total`** (Counter)
  - Description: Hangup causes
  - Attributes: `hangup.cause`, `error`

- **`genesis_channel_bridge_operations_total`** (Counter)
  - Description: Bridge operations
  - Attributes: `success`, `error`

- **`genesis_channel_dtmf_received_total`** (Counter)
  - Description: DTMF digits received
  - Attributes: `dtmf.digit`

**Call Metrics:**
- **`genesis_call_duration_seconds`** (Histogram)
  - Description: Total call duration from creation to hangup
  - Attributes: (no attributes)

**Ring Group Metrics:**
- **`genesis_ring_group_operations_total`** (Counter)
  - Description: Number of ring group operations
  - Attributes: `mode` (parallel/sequential), `has_balancer`

- **`genesis_ring_group_operation_duration_seconds`** (Histogram)
  - Description: Duration of ring group operations
  - Attributes: `mode`, `has_balancer`

- **`genesis_ring_group_results_total`** (Counter)
  - Description: Ring group operation results
  - Attributes: `mode`, `result` (answered/no_answer/error), `has_balancer`, `error` (if error)

**Load Balancer Monitoring:**

When using load balancers with ring groups, monitoring is integrated into the existing metrics:

- The `has_balancer` attribute in ring group metrics indicates when load balancing is active
- The `ring_group.balanced` span attribute shows when destinations were reordered by load
- Track `ring_group.results` with `has_balancer=true` to monitor load-balanced operations
- The `ring_group.answered_dial_path` attribute shows which destination answered, useful for analyzing load distribution

For programmatic access to load counts per destination, use the load balancer's `get_count()` method or export custom metrics from your application based on these values.

**Timeout Metrics:**
- **`genesis_timeouts_total`** (Counter)
  - Description: Number of timeouts
  - Attributes: `timeout.type` (wait, command, connection), `timeout.operation`, `timeout.duration`

## Channel lifecycle metrics

These metrics describe what a call is doing across its lifecycle — from the
moment FreeSWITCH creates the channel until it is destroyed. Use them together
with the [tracing](./tracing) spans to follow a call end to end and to correlate
it with the passive sniffer (see [Sniffer correlation](./tracing#sniffer-correlation-sipcall_id-join)).

- **`genesis.calls.active`** (UpDownCounter)
  - Description: Number of calls currently active, by state and direction. Goes up when a channel is created and back down when it is destroyed.
  - Attributes: `channel.state`, `direction`

- **`genesis.channel.bridge.events`** (Counter)
  - Description: Bridges established and torn down, from the authoritative `CHANNEL_BRIDGE` / `CHANNEL_UNBRIDGE` events.
  - Attributes: `bridge.result` (`established`, `unbridged`), `hangup.cause`

- **`genesis.channel.transfers`** (Counter)
  - Description: Call transfers observed through the `sofia::transferor` and `sofia::transferee` events.
  - Attributes: `transfer.type` (`blind`, `attended`), `transfer.role`

- **`genesis.channel.codec.changes`** (Counter)
  - Description: Codec renegotiations observed through `CODEC` events.
  - Attributes: `channel.read_codec`, `channel.write_codec`

- **`genesis.dialplan.applications`** (Counter)
  - Description: Dialplan applications executed, from `CHANNEL_EXECUTE` and `CHANNEL_EXECUTE_COMPLETE`.
  - Attributes: `application.name`, `application.result` (`started`, `success`, `fail`)

- **`genesis.channel.hangup.causes.q850`** (Counter)
  - Description: Hangup causes grouped by Q.850 code.
  - Attributes: `hangup.cause.q850`

- **`genesis.event.processing.duration`** (Histogram)
  - Description: How long it takes to dispatch a single event through the processors and routing.
  - Attributes: `event.name`

- **`genesis.events.without_sip_call_id`** (Counter)
  - Description: Channel events that arrived without a `variable_sip_call_id`. A high value means the Genesis trace and the sniffer trace cannot be joined for those calls.
  - Attributes: (none)

## Session, consumer, load balancer and queue metrics

- **`genesis.session.commands`** (Counter)
  - Description: `sendmsg` commands sent through a session, by application.
  - Attributes: `application.name`

- **`genesis.session.command.duration`** (Histogram)
  - Description: How long a session `sendmsg` command takes to complete.
  - Attributes: `application.name`

- **`genesis.consumer.handlers`** (Counter)
  - Description: How many times a consumer handler was invoked, by event.
  - Attributes: `event.name`

- **`genesis.loadbalancer.selections`** (Counter)
  - Description: Destinations picked by the load balancer, including when it falls back to the first available destination.
  - Attributes: `loadbalancer.backend`, `loadbalancer.result` (`selected`, `fallback`)

- **`genesis.loadbalancer.errors`** (Counter)
  - Description: Errors raised while selecting a destination.
  - Attributes: `loadbalancer.backend`, `error`

- **`genesis.commands.queue.depth`** (ObservableGauge)
  - Description: How many command replies are still pending. Useful to spot backpressure on the command path.
  - Attributes: (none)

- **`genesis.events.queue.depth`** (ObservableGauge)
  - Description: How many events are waiting to be processed. Useful to spot backpressure on the event path.
  - Attributes: (none)
