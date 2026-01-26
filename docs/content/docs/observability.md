---
title: Observability
weight: 60
---

Genesis includes built-in **OpenTelemetry** instrumentation for tracing, logging, and metrics, providing comprehensive observability for your FreeSWITCH applications.

## Tracing

Genesis automatically generates spans for connections, commands, and events. The library uses `opentelemetry-api` to emit traces. To collect and visualize traces, configure the OpenTelemetry SDK with an exporter.

### Automatic Spans

Genesis automatically creates spans for the following operations:

**Connection Spans:**
- **`inbound_connect`** (`Inbound` module)
  - Description: Connection to FreeSWITCH
  - Attributes: `net.peer.name`, `net.peer.port`

- **`outbound_handle_connection`** (`Outbound` module)
  - Description: Handling incoming calls
  - Attributes: `net.peer.name`, `net.peer.port`

**Protocol Spans:**
- **`send_command`** (`Protocol` module)
  - Description: Sending ESL commands
  - Attributes: `command.name`, `command.reply`

- **`process_event`** (`Protocol` module)
  - Description: Processing received events
  - Attributes: `event.name`, `event.uuid`, `event.header.*`

**Channel Operation Spans:**
- **`channel.create`** (`Channel` module)
  - Description: Creating a new channel
  - Attributes: `channel.dial_path`, `channel.uuid`, `channel.has_variables`

- **`channel.answer`** (`Channel` module)
  - Description: Answering a call
  - Attributes: `channel.uuid`, `channel.state`, `channel.answer.success`, `channel.answer.duration`

- **`channel.hangup`** (`Channel` module)
  - Description: Hanging up a call
  - Attributes: `channel.uuid`, `channel.state`, `hangup.cause`, `call.duration`

- **`channel.bridge`** (`Channel` module)
  - Description: Bridging two channels
  - Attributes: `channel.uuid`, `channel.other_uuid`, `channel.state`, `channel.bridge.success`

- **`channel.playback`** (`Channel` module)
  - Description: Playing audio file
  - Attributes: `channel.uuid`, `playback.path`, `playback.block`

- **`channel.say`** (`Channel` module)
  - Description: Text-to-speech
  - Attributes: `channel.uuid`, `say.module`, `say.kind`, `say.method`

- **`channel.play_and_get_digits`** (`Channel` module)
  - Description: Playing and collecting digits
  - Attributes: `channel.uuid`, `play_and_get_digits.file`, `play_and_get_digits.tries`

- **`channel.park`** (`Channel` module)
  - Description: Parking a channel
  - Attributes: `channel.uuid`, `channel.state`

- **`channel.wait`** (`Channel` module)
  - Description: Waiting for state/event
  - Attributes: `channel.uuid`, `wait.target`, `wait.timeout`, `wait.type`, `wait.result`

- **`channel.dtmf.received`** (`Channel` module)
  - Description: DTMF digit received
  - Attributes: `channel.uuid`, `dtmf.digit`, `dtmf.handled`

**Ring Group Spans:**
- **`ring_group.ring`** (`RingGroup` module)
  - Description: Ringing a group of destinations
  - Attributes: `ring_group.mode`, `ring_group.size`, `ring_group.timeout`, `ring_group.has_balancer`, `ring_group.has_variables`, `ring_group.balanced`, `ring_group.result`, `ring_group.duration`, `ring_group.answered_uuid`, `ring_group.answered_dial_path`, `ring_group.error` (if error)

### Configuration

Install the OpenTelemetry SDK:

```bash
pip install opentelemetry-sdk
```

{{< tabs >}}

  {{< tab name="Console" >}}
  **Console Exporter** (Development)

  ```python
  import asyncio
  from genesis import Inbound
  from opentelemetry import trace
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

  provider = TracerProvider()
  processor = SimpleSpanProcessor(ConsoleSpanExporter())
  provider.add_span_processor(processor)
  trace.set_tracer_provider(provider)

  async def main():
      async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
          await client.send("uptime")

  asyncio.run(main())
  ```
  {{< /tab >}}

  {{< tab name="Jaeger" >}}
  **Jaeger Exporter** (Production)

  ```bash
  pip install opentelemetry-exporter-jaeger
  ```

  ```python
  from opentelemetry import trace
  from opentelemetry.exporter.jaeger.thrift import JaegerExporter
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor

  provider = TracerProvider()
  jaeger_exporter = JaegerExporter(
      agent_host_name="localhost",
      agent_port=6831,
  )
  provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
  trace.set_tracer_provider(provider)
  ```
  {{< /tab >}}

  {{< tab name="OTLP" >}}
  **OTLP Exporter** (Production)

  ```bash
  pip install opentelemetry-exporter-otlp
  ```

  ```python
  from opentelemetry import trace
  from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
  from opentelemetry.sdk.trace import TracerProvider
  from opentelemetry.sdk.trace.export import BatchSpanProcessor

  provider = TracerProvider()
  otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
  provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
  trace.set_tracer_provider(provider)
  ```
  {{< /tab >}}

{{< /tabs >}}

{{< callout type="info" >}}
If you're using frameworks like FastAPI that already configure OpenTelemetry, Genesis will automatically attach its spans to the active trace.
{{< /callout >}}

### Event Header Attributes

All event headers are flattened into `event.header.{snake_case_name}` attributes, allowing for easy filtering and querying:

```python
# Event header: "Event-Subclass" → attribute: "event.header.event_subclass"
# Event header: "Channel-State" → attribute: "event.header.channel_state"
```

## Logging

Genesis provides structured logging with automatic trace correlation.

### Log Correlation

When logs are generated within an active trace span, Genesis automatically injects `trace_id` and `span_id` into log records.

**Default Output:**
```text
[10:34:43] INFO     This is a log message (trace_id=... span_id=...)
```

### JSON Logging

Enable JSON logging for production environments using the `--json` flag:

```bash
genesis --json consumer ./app.py
```

**JSON Output:**
```json
{
  "timestamp": "2026-01-16T13:35:11.813625+00:00",
  "level": "INFO",
  "message": "This is a log message",
  "logger": "genesis.logger",
  "trace_id": "eee4dfc73530a13a846ec8f1e61561f4",
  "span_id": "639ec6ffc3f956f2"
}
```

## Metrics

Genesis exposes metrics via OpenTelemetry that can be scraped by Prometheus.

### CLI Automatic Exposure

{{< callout type="info" >}}
When running via CLI, a Prometheus metrics server starts automatically.
{{< /callout >}}

The metrics server runs on port 8000 by default (configurable via `GENESIS_METRICS_PORT`):

```bash
export GENESIS_METRICS_PORT=9090
genesis consumer ./app.py
```

Access metrics at `http://localhost:8000/metrics` (or your configured port).

### Available Metrics

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

### Manual Configuration

If using Genesis as a library (without CLI), configure the exporter manually:

```python
import asyncio
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server
from genesis import Inbound

start_http_server(8000)

metric_reader = PrometheusMetricReader()
provider = MeterProvider(
    resource=Resource.create({"service.name": "genesis-app"}),
    metric_readers=[metric_reader],
)
metrics.set_meter_provider(provider)

async def main():
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        await client.send("uptime")
        await asyncio.sleep(60)  # Keep running

asyncio.run(main())
```
