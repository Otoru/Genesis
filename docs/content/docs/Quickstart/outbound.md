---
title: Outbound Socket
weight: 30
---

Outbound Socket mode allows you to create dialplan-driven services that control calls in real-time. FreeSWITCH connects to your application when a call matches a dialplan entry, giving you full control over the call flow.

## Basic Example

```python
import asyncio
from genesis import Outbound

async def handler(session):
    await session.channel.answer()
    await session.channel.playback('ivr/ivr-welcome')
    await session.channel.hangup()

app = Outbound(handler, "127.0.0.1", 5000)

asyncio.run(app.start())
```

## Dialplan Configuration

{{< callout type="warning" >}}
Your FreeSWITCH dialplan must be configured to route calls to your application.
{{< /callout >}}

Add an entry to your FreeSWITCH dialplan that routes calls to your application:

```xml
<extension name="outbound-socket">
   <condition>
      <action application="socket" data="127.0.0.1:5000 async full"/>
   </condition>
</extension>
```

## How it works

```mermaid
sequenceDiagram
    participant Caller
    participant FreeSWITCH
    participant App
    participant Handler
    
    Caller->>FreeSWITCH: Incoming Call
    FreeSWITCH->>FreeSWITCH: Match Dialplan
    FreeSWITCH->>App: Connect (ESL)
    App->>Handler: Create Session
    Handler->>FreeSWITCH: answer()
    FreeSWITCH->>Caller: Call Answered
    Handler->>FreeSWITCH: playback()
    FreeSWITCH->>Caller: Play Audio
    Handler->>FreeSWITCH: hangup()
    FreeSWITCH->>Caller: Call Ended
    FreeSWITCH-->>App: Session Closed
```

{{% steps %}}

### Dialplan Match

FreeSWITCH matches a call to your dialplan entry.

### Connection

FreeSWITCH connects to your application at the specified host and port.

### Session Handler

Your handler function receives a `Session` object representing the call.

### Channel Access

Each `Session` has a `channel` attribute that represents the call leg associated with the session. This channel is automatically initialized when FreeSWITCH connects to your application. You use `session.channel` to control the call.

### Call Control

You control the call using `session.channel` methods like `answer()`, `playback()`, `hangup()`, etc.

### Session Lifecycle

The session remains active until the call ends.

{{% /steps %}}

## Advanced Example

Building an IVR with `onDTMF()` and `wait()`:

```python
import asyncio
from genesis import Outbound
from genesis.exceptions import TimeoutError

async def handler(session):
    await session.channel.answer()
    
    # Register handlers for each menu option
    @session.channel.onDTMF("1")
    async def option1(dtmf: str):
        await session.channel.playback('ivr/ivr-option-1')
    
    @session.channel.onDTMF("2")
    async def option2(dtmf: str):
        await session.channel.playback('ivr/ivr-option-2')
    
    @session.channel.onDTMF("3")
    async def option3(dtmf: str):
        await session.channel.playback('ivr/ivr-option-3')
    
    @session.channel.onDTMF("4")
    async def option4(dtmf: str):
        await session.channel.playback('ivr/ivr-option-4')
    
    # Play menu prompt
    await session.channel.playback('ivr/ivr-welcome')
    
    # Wait for DTMF input with 10 second timeout
    try:
        await session.channel.wait("DTMF", timeout=10.0)
        # The corresponding handler was already executed automatically
    except TimeoutError:
        await session.channel.playback('ivr/ivr-timeout')
        await session.channel.hangup()

app = Outbound(handler, "127.0.0.1", 5000)
asyncio.run(app.start())
```

## Connection Management

Genesis provides advanced control over the socket connection lifecycle and event subscription.

### Linger

By default, FreeSWITCH closes the socket connection immediately when the call hangs up. The `linger` option (enabled by default in `Outbound`) keeps the connection open for a short period after hangup, allowing your application to receive the final events (like `CHANNEL_HANGUP_COMPLETE`) and perform post-call processing.

```python
# Linger is enabled by default
app = Outbound(handler, "127.0.0.1", 5000, linger=True)
```

### Event Filtering

Genesis uses a flexible filtering system instead of the restrictive `myevents` command.

```python
# Events are enabled by default
app = Outbound(handler, "127.0.0.1", 5000, events=True)
```

{{% steps %}}

### Initial Filter

Genesis automatically sends `filter Unique-ID <uuid>` to whitelist events for the current session.

### Event Subscription

It then subscribes to all events (`event plain all`).

### Dynamic Filtering

Because `filter` works as an additive whitelist (appending to the stack), you can simply send new `filter` commands sequentially to add more UUIDs. You do **not** need to resend the previous ones.

```python
# To add a B-leg later:
await session.send(f"filter Unique-ID {b_leg_uuid}")
```

{{% /steps %}}

{{< callout type="info" >}}
**Source Code Verification**

This behavior is confirmed by the FreeSWITCH source code in `mod_event_socket.c`, where `switch_event_add_header_string` uses `SWITCH_STACK_BOTTOM` to append new filters to the list rather than overwriting them.

[View on GitHub](https://github.com/signalwire/freeswitch/blob/v1.10/src/mod/event_handlers/mod_event_socket/mod_event_socket.c#L803)
{{< /callout >}}

This approach ensures you receive all necessary events for the main call while retaining the ability to track related channels without flood or restriction.

## Use Cases

- Interactive Voice Response (IVR) systems
- Call routing and forwarding
- Call recording and monitoring
- Custom call handling logic
- Integration with external services
