---
title: Quickstart
weight: 10
---

# Quickstart

Genesis can be used in three main ways. Below, we briefly cover each of them.

## Inbound Socket Mode

An Inbound Socket application with Genesis looks like this:

```python
import asyncio
from genesis import Inbound

async def uptime():
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        return await client.send("uptime")

async def main():
    response = await uptime()
    print(response)

asyncio.run(main())
```

**What does this code do?**

- We create an `async` function named `uptime`.
- Inside it, we use the `Inbound` class as an asynchronous context manager to connect to FreeSWITCH.
- The connection is established to `127.0.0.1` on port `8021` with the password `ClueCon`.
- With the connection established, we send the `uptime` command to the server.
- In the `main` function, we call `uptime` and print the response.

## Consumer Mode

An event handler application with Genesis looks like this:

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

**What does this code do?**

- We create an application with the `Consumer` class.
- The connection is established to `127.0.0.1` on port `8021` with the password `ClueCon`.
- We use the `@app.handle` decorator to define a `handler` function that will process all received `HEARTBEAT` events.
- We start the consumer with `app.start()`.

## Outbound Socket Mode

An Outbound Socket application with Genesis looks like this:

```python
import asyncio
from genesis import Outbound

async def handler(session):
    await session.answer()
    await session.playback('ivr/ivr-welcome')
    await session.hangup()

app = Outbound("127.0.0.1", 5000, handler)

asyncio.run(app.start())
```

Your dialplan should have an entry similar to this:

```xml
<extension name="outbound-socket">
   <condition>
      <action application="socket" data="127.0.0.1:5000 async full"/>
   </condition>
</extension>
```

**What does this code do?**

- We define a `handler` function that will process all sessions established with the application.
- We create an application that listens on `127.0.0.1` at port `5000` and uses the `handler` function to process connections.
- We start the application with `app.start()`.