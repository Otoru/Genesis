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

These spans follow a call across its FreeSWITCH lifecycle, from channel
creation to destruction. They carry the channel UUIDs and the SIP correlation
key on the span (see [Cross-system correlation](#cross-system-correlation-sipcall_id)).

- **`freeswitch.channel.create`**
  - Description: A new channel was created
  - Attributes: `channel.uuid`, `channel.call_uuid`, `channel.direction`, `sip.call_id`, `channel.destination_number`, `channel.context`

- **`freeswitch.channel.progress`** / **`freeswitch.channel.progress_media`**
  - Description: The call is progressing / early media is flowing
  - Attributes: `channel.state`, `answer.state`, codec names

- **`freeswitch.channel.answer`**
  - Description: The call was answered
  - Attributes: `channel.state`, `answer.state`, codec names

- **`freeswitch.channel.bridge`**
  - Description: Two channels were bridged together
  - Attributes: `bridge.a_uuid`, `bridge.b_uuid`, `other_leg.*`
  - Events: `bridge.established`

- **`freeswitch.channel.unbridge`**
  - Description: The bridge between two channels was torn down
  - Attributes: `bridge.a_uuid`, `bridge.b_uuid`, `hangup.cause`
  - Events: `bridge.torn_down`

- **`freeswitch.channel.hangup`**
  - Description: The channel is hanging up
  - Attributes: `hangup.cause`, `channel.state`
  - Events: `hangup.cause.<normalized>`

- **`freeswitch.channel.hangup_complete`**
  - Description: Hangup is complete and the call is finalized
  - Attributes: `hangup.cause`, `hangup.cause.q850`
  - Events: `call.finalized`

- **`freeswitch.channel.destroy`**
  - Description: The channel was destroyed
  - Attributes: `channel.uuid`, `sip.call_id`

- **`freeswitch.channel.execute`** / **`freeswitch.channel.execute_complete`**
  - Description: A dialplan application started / finished executing
  - Attributes: `application.name`, `application.uuid`, `application.data` / `application.response`
  - Events: `app.<name>.done`

- **`freeswitch.channel.codec`**
  - Description: The channel negotiated (or renegotiated) its codecs
  - Attributes: `channel.read_codec.*`, `channel.write_codec.*`

- **`freeswitch.call.update`**
  - Description: The caller ID or bridged state changed
  - Attributes: `bridged.to`, `caller.transfer_source`
  - Events: `caller_id.mutated`

**CUSTOM Subclass Spans:**

These spans cover the `CUSTOM` event subclasses FreeSWITCH emits for
transfers, registrations, callcenter, conference and valet parking.

- **`freeswitch.sofia.transfer`**
  - Description: A call transfer was observed
  - Attributes: `transfer.role` (`transferor` / `transferee`), `transfer.type` (`blind` / `attended`)
  - Events: `transfer.initiated`

- **`freeswitch.sofia.register`** / **`freeswitch.sofia.reinvite`** / **`freeswitch.sofia.replaced`**
  - Description: A SIP registration, reinvite or replace was observed
  - Attributes: `register.aor`, `register.action`, `gateway.name` / `gateway.state`, `sofia.profile`

- **`freeswitch.callcenter.info`**
  - Description: A callcenter queue event
  - Attributes: `cc.queue`, `cc.action`, `cc.agent`, `cc.member_uuid`, `cc.count`, `cc.selection`

- **`freeswitch.conference.maintenance`** / **`freeswitch.conference.cdr`**
  - Description: A conference maintenance or CDR event
  - Attributes: `conference.name`, `conference.profile`, `conference.action`, `conference.member_id`

- **`freeswitch.valet.info`**
  - Description: A valet parking event
  - Attributes: `valet.lot`, `valet.extension`, `valet.action`, `bridge.to_uuid`

**Session / Consumer / Queue Spans:**

- **`session.sendmsg`** (`Session` module)
  - Description: A `sendmsg` command was sent through a session
  - Attributes: `channel.uuid`, `application.name`, `application.uuid`, `application.block`

- **`session.await_complete`** (`Session` module)
  - Description: Waits for a blocking `sendmsg` to complete (child of `session.sendmsg` when `block=True`)
  - Attributes: `channel.uuid`, `application.uuid`

- **`consumer.start`** / **`consumer.stop`** (`Consumer` module)
  - Description: The consumer subscribed to events / stopped
  - Attributes: `consumer.host`, `consumer.port`

- **`queue.wait_and_acquire`** (`Queue` module)
  - Description: Waiting to acquire an item from the queue
  - Attributes: `queue.id`, `queue.item_id`, `queue.depth` (span attribute, not a metric label)

## Cross-system correlation (sip.call_id)

Every `freeswitch.channel.*` span carries **`sip.call_id`**, taken from the ESL
`variable_sip_call_id` header. This is the standard SIP `Call-ID` header, a
stable per-call identifier that any other SIP observer of the same call will
also have. That makes it a natural join key when you want to correlate Genesis
traces with traces from another system that observed the same call.

- The join happens **at the observability backend** (Grafana/Tempo or similar),
  by filtering or grouping on `sip.call_id` — not in code.
- Cross-leg grouping: bridge spans carry **`bridge.a_uuid`** and
  **`bridge.b_uuid`**, so the a-leg and b-leg of a call can be tied together.
- The `genesis.events.without_sip_call_id` metric counts channel events that
  arrived without the correlation key — a signal that those calls cannot be
  joined to another system's view.

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
