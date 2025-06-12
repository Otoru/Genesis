---
title: Quickstart
weight: 1
---
# Quickstart

Genesis can be used in three main ways. Below we will briefly address each of them.

## Inbound Socket Mode

An inbound socket app made with Genesis looks like this:

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

So what does this code do?

- We create an async function with `uptime` name.
- In it, we use the `Inbound` class as an asynchronous context manager to connect to the freeswitch.
- The connection is made at address `127.0.0.1` on port `8021` and authentication is done with the `ClueCon` password.
- With the connection established, we send the `uptime` command to the server.
- In the main function, we call this function to display the command return on the screen.

## Incoming Event handler

An event handler app made with Genesis looks like this:

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

So what does this code do?

- We create an application with the `Consumer` class.
- The connection is established using the address `127.0.0.1` on port `8021` and authentication is done with the `ClueCon` password.
- We use the `@app.handler` decorator to define a `handler` function and define that it will be used to handle all `HEARTBEAT` events that are received.
- We start the consumer with the `app.start()` instruction.

## Outbound Socket Mode

An outbound socket app made with Genesis looks like this:

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

And the dialplan should have an entry similar to this:

```xml
<extension name="out socket">
   <condition>
      <action application="socket" data="127.0.0.1:5000 async full"/>
   </condition>
</extension>
```

So what does this code do?

- We define a `handler` function that will handle all sessions established with the application.
- We create an application that will listen on address `127.0.0.1`, on port `5000` and will use the `handler` function to handle connections.
- We start the application with the `app.start()` instruction.
