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

**ESL Channel Lifecycle Spans (`freeswitch.channel.*`):**
- Emitted by the `channel_lifecycle_processor` for the semantic FreeSWITCH channel lifecycle. They carry the channel UUIDs and the sniffer correlation key on the span (see [Sniffer correlation](#sniffer-correlation-sipcall_id-join)).
- **`freeswitch.channel.create`** — `channel.uuid`, `channel.call_uuid`, `channel.direction`, `sip.call_id`, `channel.destination_number`, `channel.context`
- **`freeswitch.channel.progress`** / **`.progress_media`** — `channel.state`, `answer.state`, codec names
- **`freeswitch.channel.answer`** — `channel.state`, `answer.state`, codec names
- **`freeswitch.channel.bridge`** — `bridge.a_uuid`, `bridge.b_uuid`, `other_leg.*`, span event `bridge.established`
- **`freeswitch.channel.unbridge`** — `bridge.a_uuid`, `bridge.b_uuid`, `hangup.cause`, span event `bridge.torn_down`
- **`freeswitch.channel.hangup`** — `hangup.cause`, `channel.state`, span event `hangup.cause.<normalized>`
- **`freeswitch.channel.hangup_complete`** — `hangup.cause`, `hangup.cause.q850`, span event `call.finalized`
- **`freeswitch.channel.destroy`** — `channel.uuid`, `sip.call_id`
- **`freeswitch.channel.execute`** / **`.execute_complete`** — `application.name`, `application.uuid`, `application.data`/`application.response`, span event `app.<name>.done`
- **`freeswitch.channel.codec`** — `channel.read_codec.*`, `channel.write_codec.*`
- **`freeswitch.call.update`** — `bridged.to`, `caller.transfer_source`, span event `caller_id.mutated`

**CUSTOM Subclass Spans:**
- Emitted by the `custom_subclass_processor` for `CUSTOM` events.
- **`freeswitch.sofia.transfer`** — `transfer.role` (`transferor`/`transferee`), `transfer.type` (`blind`/`attended`), span event `transfer.initiated`
- **`freeswitch.sofia.register`** / **`.reinvite`** / **`.replaced`** — `register.aor`, `register.action`, `gateway.name`/`gateway.state`, `sofia.profile`
- **`freeswitch.callcenter.info`** — `cc.queue`, `cc.action`, `cc.agent`, `cc.member_uuid`, `cc.count`, `cc.selection`
- **`freeswitch.conference.maintenance`** / **`.cdr`** — `conference.name`, `conference.profile`, `conference.action`, `conference.member_id`
- **`freeswitch.valet.info`** — `valet.lot`, `valet.extension`, `valet.action`, `bridge.to_uuid`

**Session / Consumer / Queue Spans:**
- **`session.sendmsg`** (`Session` module) — `channel.uuid`, `application.name`, `application.uuid`, `application.block`
- **`session.await_complete`** (`Session` module) — child span of `session.sendmsg` when `block=True`; `channel.uuid`, `application.uuid`
- **`consumer.start`** / **`consumer.stop`** (`Consumer` module) — `consumer.host`, `consumer.port`
- **`queue.wait_and_acquire`** (`Queue` module) — `queue.id`, `queue.item_id`, `queue.depth` (span attribute, not a metric label)

## Sniffer correlation (sip.call_id join)

Correlation with the passive sniffer (Otoru/sniffer) is **attribute-based and
happens at the observability backend (Grafana/Tempo), not in code**:

- Every `freeswitch.channel.*` span carries **`sip.call_id`** (= the ESL
  `variable_sip_call_id` header), which matches the sniffer's **`voip.call_id`**.
- Join the two traces in Grafana/Tempo by filtering/grouping on that attribute.
- Cross-leg grouping: bridge spans carry **`bridge.a_uuid`** and
  **`bridge.b_uuid`**, so the a-leg and b-leg of a call can be tied together.
- The `genesis.events.without_sip_call_id` metric counts channel events that
  lack the correlation key (a correlation-gap signal).

W3C `traceparent` / `X-Tracespan` propagation to the sniffer is intentionally
**out of scope**; the attribute join is sufficient and requires no sniffer
changes.

The lifecycle/CUSTOM processors are on by default. Opt out with
`GENESIS_TRACE_ESL_LIFECYCLE=0` or `GENESIS_TRACE_CUSTOM_SUBCLASSES=0`.

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
