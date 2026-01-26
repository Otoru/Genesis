---
title: Group Call
weight: 30
parent: Examples
---

Simultaneous originate example that calls multiple destinations and bridges with the first one to answer.

## Example Code

```python {filename="examples/group_call.py" base_url="https://github.com/Otoru/Genesis/blob/main"}
import asyncio
import os

from genesis import Inbound, RingGroup, RingMode, Channel
from genesis.types import ChannelState

FS_HOST = os.getenv("FS_HOST", "127.0.0.1")
FS_PORT = int(os.getenv("FS_PORT", "8021"))
FS_PASSWORD = os.getenv("FS_PASSWORD", "ClueCon")


async def main() -> None:
    caller_dial_path = "user/1000"
    group = ["user/1001", "user/1002", "user/1003"]

    async with Inbound(FS_HOST, FS_PORT, FS_PASSWORD) as client:
        # Ring group in parallel mode
        answered = await RingGroup.ring(
            client, group, RingMode.PARALLEL, timeout=30.0
        )

        if answered:
            # Create caller channel and bridge with answered callee
            caller = await Channel.create(client, caller_dial_path)
            await caller.wait(ChannelState.EXECUTE)
            await caller.bridge(answered)

            # Handle the call...
            await asyncio.sleep(5)

            # Hang up
            await answered.hangup()
            await caller.hangup()


if __name__ == "__main__":
    asyncio.run(main())
```

## How It Works

This example demonstrates how to use `RingGroup` to implement simultaneous originate:

1. Uses `RingGroup.ring()` with `RingMode.PARALLEL` to call all destinations simultaneously
2. The method automatically waits for the first callee to answer and returns that channel
3. Channels that didn't answer are automatically hung up
4. Creates the caller channel and bridges it with the answered callee

### Ring Modes

`RingGroup` supports two modes:

- **`RingMode.PARALLEL`**: Calls all destinations simultaneously. The first one to answer wins, and all others are automatically hung up.
- **`RingMode.SEQUENTIAL`**: Calls destinations one at a time. Tries the next one only if the current one doesn't answer within the timeout.

### Flow Diagram

```mermaid
sequenceDiagram
    participant App
    participant FreeSWITCH
    participant Caller as Caller<br/>(user/1000)
    participant Callee1 as Callee 1<br/>(user/1001)
    participant Callee2 as Callee 2<br/>(user/1002)
    participant Callee3 as Callee 3<br/>(user/1003)
    
    App->>FreeSWITCH: Create caller channel
    FreeSWITCH->>Caller: Ring
    Caller->>FreeSWITCH: Answer
    FreeSWITCH-->>App: Caller answered
    
    par Simultaneous Originate
        App->>FreeSWITCH: Create callee 1 channel
        App->>FreeSWITCH: Create callee 2 channel
        App->>FreeSWITCH: Create callee 3 channel
    end
    
    par All Callees Ringing
        FreeSWITCH->>Callee1: Ring
        FreeSWITCH->>Callee2: Ring
        FreeSWITCH->>Callee3: Ring
    end
    
    Callee2->>FreeSWITCH: Answer (first)
    FreeSWITCH-->>App: Callee 2 answered
    
    App->>FreeSWITCH: Cancel callee 1 & 3
    FreeSWITCH->>Callee1: Hangup
    FreeSWITCH->>Callee3: Hangup
    
    App->>FreeSWITCH: Bridge caller ↔ callee 2
    FreeSWITCH->>Caller: Connected
    FreeSWITCH->>Callee2: Connected
    Note over Caller,Callee2: Call in progress
```

This pattern is useful for scenarios like:
- **Ring groups**: Call multiple people at once, connect to whoever answers first
- **Failover**: Try multiple destinations simultaneously, use the first available
- **Load distribution**: Distribute calls across multiple agents

## Running the Example

{{% steps %}}

### 1. Start FreeSWITCH

Make sure FreeSWITCH is running in Docker (see [Examples environment]({{< relref "../Examples/_index.md" >}})).

### 2. Run the Example

```bash
python examples/group_call.py
```

The example will:
- Ring the group `["user/1001", "user/1002", "user/1003"]` in parallel mode
- Wait for the first callee to answer (or timeout after 30 seconds)
- Create and bridge the caller (`user/1000`) with the answered callee
- Hang up all channels after 5 seconds

### 3. Test with Multiple Users

To test this properly, you'll need multiple SIP clients registered:
- User `1000` (caller)
- Users `1001`, `1002`, `1003` (callees)

The first callee to answer will be connected to the caller.

{{% /steps %}}
