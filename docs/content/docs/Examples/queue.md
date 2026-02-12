---
title: Queue
weight: 25
parent: Examples
---

Outbound example: one extension calls another through the app. The caller hears hold music (or a message) until a queue slot is free, then we bridge them to the callee. Only one bridge at a time, so you keep control (e.g. one agent per queue).

## Example Code

```python {filename="examples/queue.py" base_url="https://github.com/Otoru/Genesis/blob/main"}
"""
Queue example.

One extension calls another via the app: the caller is held (music or message)
until a queue slot is free, then we bridge them to the callee. Only one
bridge at a time so you keep control (e.g. one agent per queue).
"""

import asyncio
import os

from genesis import Outbound, Session, Queue, Channel
from genesis.types import ChannelState

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "9696"))
CALLEE = "user/1001"
HOLD_SOUND = os.getenv("HOLD_SOUND", "local_stream://moh")

queue = Queue()  # in-memory by default


async def handler(session: Session) -> None:
    if session.channel is None:
        return
    await session.channel.answer()
    await session.channel.playback(HOLD_SOUND, block=False)

    async with queue.slot("support"):
        callee = await Channel.create(session, CALLEE)
        await callee.wait(ChannelState.EXECUTE, timeout=30.0)
        await session.channel.bridge(callee)


async def main() -> None:
    server = Outbound(handler=handler, host=HOST, port=PORT)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
```

## Flow

{{% steps %}}

### FreeSWITCH sends the call

FreeSWITCH sends the call to your app (outbound socket).

### Answer and play hold sound

We answer and start playing a hold sound (`playback(..., block=False)`), so the caller hears it while waiting.

### Wait for a queue slot

The handler waits for a slot in the `"support"` queue (`async with queue.slot("support")`). If another call is already in the slot, this call waits (caller keeps hearing the hold sound).

### Originate callee and bridge

When we get the slot, we originate the callee (`Channel.create(session, CALLEE)`), wait for them to answer, then bridge the caller to the callee. The bridge replaces the hold playback.

### Release the slot

When the handler leaves the `async with` block, the slot is released and the next waiting caller can be served.

{{% /steps %}}

## Running the Example

{{% steps %}}

### Start FreeSWITCH

Make sure FreeSWITCH is running (see [Examples environment]({{< relref "../Examples/_index.md" >}})).

### Run the queue example

```bash
python examples/queue.py
```

### Make test calls

- You need two SIP clients: caller and callee (`user/1001`). See [Examples environment]({{< relref "../Examples/_index.md" >}}) (Docker includes MOH).
- Call the number that hits this dialplan. You hear hold music until your turn, then you're bridged to the callee.
- Place a second call while the first is still connected: the second caller hears hold music until the first call ends.

### View Logs

To see what's happening in FreeSWITCH:

```bash
docker exec -it genesis-freeswitch fs_cli -x "show channels"
docker logs genesis-freeswitch -f
```

{{% /steps %}}

## Related

- [Queue]({{< relref "../Tools/queue/_index.md" >}}) - Queue API and backends
- [Outbound Socket]({{< relref "../Quickstart/outbound.md" >}}) - Outbound basics
- [Channel]({{< relref "../Tools/channel.md" >}}) - Creating channels and bridge
