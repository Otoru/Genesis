---
title: Consumer
weight: 20
---

Consumer mode enables you to process FreeSWITCH events asynchronously using intuitive decorators. This mode is perfect for monitoring, logging, and real-time event processing.

## Basic Example

```python
import asyncio
from genesis import Consumer

app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("HEARTBEAT")
async def handler(event):
    await asyncio.sleep(0.001)
    print(event)

asyncio.run(app.start())
```

## How it works

The `Consumer` class:

{{% steps %}}

### Connection

Establishes a persistent connection to FreeSWITCH.

### Subscription

Subscribes to events automatically.

### Routing

Routes events to registered handlers using the `@app.handle()` decorator.

### Processing

Processes multiple event types concurrently.

{{% /steps %}}

## Handling Multiple Events

You can register multiple handlers for different event types:

```python
app = Consumer("127.0.0.1", 8021, "ClueCon")

@app.handle("CHANNEL_CREATE")
async def on_channel_create(event):
    print(f"New channel created: {event.get('Channel-Call-UUID')}")

@app.handle("CHANNEL_ANSWER")
async def on_channel_answer(event):
    print(f"Channel answered: {event.get('Channel-Call-UUID')}")

@app.handle("CHANNEL_HANGUP")
async def on_channel_hangup(event):
    print(f"Channel hung up: {event.get('Channel-Call-UUID')}")

asyncio.run(app.start())
```

## Use Cases

- Real-time monitoring and logging
- Event-driven applications
- Call tracking and analytics
- System health monitoring
- Custom event processing pipelines
