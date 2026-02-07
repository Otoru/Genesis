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
