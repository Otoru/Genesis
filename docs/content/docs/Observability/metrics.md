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

**ESL Lifecycle Metrics (sniffer correlation):**

These metrics are emitted by the lifecycle/CUSTOM processors. Cardinality rule:
attributes carry low-cardinality enums only — UUIDs go on spans, never as
metric labels.

- **`genesis.calls.active`** (UpDownCounter) — Active calls by state and direction; +1 on `CHANNEL_CREATE`, -1 on `CHANNEL_DESTROY`. Attributes: `channel.state`, `direction`
- **`genesis.channel.bridge.events`** (Counter) — Authoritative bridge state from `CHANNEL_BRIDGE`/`UNBRIDGE`. Attributes: `bridge.result` (`established`/`unbridged`), `hangup.cause`
- **`genesis.channel.transfers`** (Counter) — Transfers via `sofia::transferor`/`transferee`. Attributes: `transfer.type` (`blind`/`attended`), `transfer.role`
- **`genesis.channel.codec.changes`** (Counter) — Codec renegotiations from `CODEC` events. Attributes: `channel.read_codec`, `channel.write_codec`
- **`genesis.dialplan.applications`** (Counter) — Dialplan apps from `CHANNEL_EXECUTE`/`_COMPLETE`. Attributes: `application.name`, `application.result` (`started`/`success`/`fail`)
- **`genesis.channel.hangup.causes.q850`** (Counter) — Hangup causes by Q.850 code. Attributes: `hangup.cause.q850`
- **`genesis.event.processing.duration`** (Histogram) — Duration of event dispatch (processors + routing). Attributes: `event.name`
- **`genesis.events.without_sip_call_id`** (Counter) — Channel events lacking `variable_sip_call_id` (a correlation-gap signal vs the passive sniffer). Attributes: (none)

**Session / Consumer / Load Balancer / Queue Metrics:**
- **`genesis.session.commands`** (Counter) — Session `sendmsg` commands. Attributes: `application.name`
- **`genesis.session.command.duration`** (Histogram) — Duration of session `sendmsg` commands. Attributes: `application.name`
- **`genesis.consumer.handlers`** (Counter) — Consumer handler invocations. Attributes: `event.name`
- **`genesis.loadbalancer.selections`** (Counter) — Load balancer selections. Attributes: `loadbalancer.backend`, `loadbalancer.result` (`selected`/`fallback`)
- **`genesis.loadbalancer.errors`** (Counter) — Load balancer errors. Attributes: `loadbalancer.backend`, `error`
- **`genesis.commands.queue.depth`** (ObservableGauge) — Depth of the pending command-reply queue. Attributes: (none)
- **`genesis.events.queue.depth`** (ObservableGauge) — Depth of the pending event queue. Attributes: (none)

> All metric instruments are centralized in `genesis/protocol/metrics.py`.
> Import them from there rather than re-declaring, and use the `safe_add` /
> `safe_record` helpers so a missing exporter never crashes the protocol.
