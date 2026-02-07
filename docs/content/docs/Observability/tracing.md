---
title: Tracing
weight: 10
---

Genesis automatically generates spans for connections, commands, and events. The library uses `opentelemetry-api` to emit traces. To collect and visualize traces, configure the OpenTelemetry SDK with an exporter.

## Automatic Spans

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

## Configuration

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

## Event Header Attributes

All event headers are flattened into `event.header.{snake_case_name}` attributes, allowing for easy filtering and querying:

```python
# Event header: "Event-Subclass" → attribute: "event.header.event_subclass"
# Event header: "Channel-State" → attribute: "event.header.channel_state"
```
