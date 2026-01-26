---
title: Ring Group
weight: 30
---

The `RingGroup` class provides a factory pattern for managing simultaneous or sequential call groups. It simplifies the process of calling multiple destinations and connecting to the first one that answers.

## Overview

`RingGroup` is a static factory that handles the complexity of:
- Creating multiple channels simultaneously or sequentially
- Waiting for the first destination to answer
- Automatically cleaning up channels that didn't answer
- Returning the channel that answered first

## Basic Example

```python
import asyncio
from genesis import Inbound, RingGroup, RingMode, Channel
from genesis.types import ChannelState

async def ring_group_example():
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        # Ring a group in parallel mode
        group = ["user/1001", "user/1002", "user/1003"]
        answered = await RingGroup.ring(
            client, group, RingMode.PARALLEL, timeout=30.0
        )
        
        if answered:
            # Create caller and bridge
            caller = await Channel.create(client, "user/1000")
            await caller.wait(ChannelState.EXECUTE)
            await caller.bridge(answered)
            
            # Handle the call...
            await asyncio.sleep(5)
            
            await answered.hangup()
            await caller.hangup()

asyncio.run(ring_group_example())
```

## Ring Modes

`RingGroup` supports three calling strategies that determine how destinations are contacted:

**Parallel mode** calls all destinations at the same time and connects to whoever answers first. This is ideal when you want the fastest response time and all destinations are equally important.

**Sequential mode** calls destinations one at a time, only trying the next one if the current one doesn't answer. This is useful when you have priorities or need to respect a specific order.

**Balancing mode** calls all destinations simultaneously, but uses load balancing to reorder them based on current load. This ensures even distribution across destinations when using the same balancer instance across multiple groups.

### Parallel Mode

Calls all destinations simultaneously. The first one to answer wins, and all others are automatically hung up.

```python
answered = await RingGroup.ring(
    client, 
    ["user/1001", "user/1002", "user/1003"],
    RingMode.PARALLEL,
    timeout=30.0
)
```

**Use cases:**
- Ring groups (call multiple people at once)
- Failover scenarios (try multiple destinations simultaneously)
- Load distribution (distribute calls across multiple agents)

### Sequential Mode

Calls destinations one at a time. Tries the next one only if the current one doesn't answer within the timeout.

```python
answered = await RingGroup.ring(
    client,
    ["user/1001", "user/1002", "user/1003"],
    RingMode.SEQUENTIAL,
    timeout=30.0
)
```

**Use cases:**
- Call forwarding chains
- Priority-based routing (try primary, then fallback)
- Ordered routing (respect specific sequence)

### Balancing Mode

Calls all destinations simultaneously with load balancing. Destinations are reordered based on current load before calling, ensuring even distribution.

```python
from genesis import Inbound, RingGroup, RingMode, InMemoryLoadBalancer

async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
    lb = InMemoryLoadBalancer()
    
    answered = await RingGroup.ring(
        client,
        ["user/1001", "user/1002", "user/1003"],
        RingMode.BALANCING,
        balancer=lb
    )
```

**Use cases:**
- Even call distribution across agents
- Horizontal scaling with shared load state
- Preventing destination overload

The load balancer tracks call counts globally. If the same balancer instance is used across different groups, destinations that appear in multiple groups will have their load tracked correctly.

For detailed information about load balancer backends, see [Load Balancer]({{< relref "load-balancer.md" >}}).

## Parameters

The `RingGroup.ring()` method accepts:

- `protocol`: Protocol instance (`Inbound` or `Session`)
- `group`: List of destinations to call (e.g., `["user/1001", "user/1002"]`)
- `mode`: Ring mode (default: `PARALLEL`)
  - `RingMode.PARALLEL`: Call all destinations simultaneously
  - `RingMode.SEQUENTIAL`: Call destinations one at a time
  - `RingMode.BALANCING`: Call all destinations simultaneously with load balancing
- `timeout`: Maximum time to wait for any callee to answer in seconds (default: `30.0`)
- `variables`: Optional dictionary of custom variables for callee channel creation
- `balancer`: Required for `BALANCING` mode, ignored for other modes

Returns the `Channel` that answered first, or `None` if none answered within timeout.

## Advanced Usage

### Custom Variables

Pass custom variables to all callee channels:

```python
variables = {
    "caller_id_number": "1000",
    "caller_id_name": "Support",
    "custom_header": "value"
}

answered = await RingGroup.ring(
    client,
    ["user/1001", "user/1002"],
    RingMode.PARALLEL,
    timeout=30.0,
    variables=variables
)
```

### Timeout Configuration

Configure different timeouts for different scenarios:

```python
# Short timeout for quick failover
answered = await RingGroup.ring(
    client,
    ["user/1001", "user/1002"],
    RingMode.PARALLEL,
    timeout=5.0  # 5 seconds
)

# Long timeout for important calls
answered = await RingGroup.ring(
    client,
    ["user/1001", "user/1002"],
    RingMode.PARALLEL,
    timeout=60.0  # 60 seconds
)
```

### Handling No Answer

Always check if someone answered:

```python
answered = await RingGroup.ring(
    client,
    ["user/1001", "user/1002", "user/1003"],
    RingMode.PARALLEL,
    timeout=30.0
)

if answered:
    # Someone answered - proceed with call
    caller = await Channel.create(client, "user/1000")
    await caller.wait(ChannelState.EXECUTE)
    await caller.bridge(answered)
    # ... handle call
else:
    # No one answered - handle accordingly
    print("No destination answered within timeout")
    # Maybe send to voicemail, try different group, etc.
```

### With Outbound Mode

`RingGroup` works with both `Inbound` and `Session` (outbound) protocols:

```python
from genesis import Outbound, Session, RingGroup, RingMode

async def handler(session: Session):
    # Ring a group from an outbound session
    answered = await RingGroup.ring(
        session,
        ["user/1001", "user/1002"],
        RingMode.PARALLEL,
        timeout=30.0
    )
    
    if answered:
        await session.channel.bridge(answered)

app = Outbound(handler, "127.0.0.1", 9000)
await app.start()
```

## How It Works

{{% steps %}}

### Parallel Mode Flow

1. All destinations are originated simultaneously
2. Waits for the first callee to answer
3. Automatically cancels pending tasks and hangs up channels that didn't answer
4. Returns the channel that answered first

### Sequential Mode Flow

1. Originates the first destination
2. Waits for the channel to reach `EXECUTE` state
3. If answered, returns that channel immediately
4. If timeout, hangs up current channel and tries the next destination
5. Continues until someone answers or all destinations are exhausted

### Balancing Mode Flow

1. Reorders destinations based on current load (least loaded first)
2. Increments load count for all destinations
3. Originates all destinations simultaneously in balanced order
4. Waits for the first callee to answer
5. Decrements load count for answered destination
6. Decrements load count for all destinations that didn't answer
7. Returns the channel that answered first

{{% /steps %}}

## Best Practices

1. Always check for `None` - the method returns `None` if no one answered
2. Set appropriate timeouts - too short may cause premature failures, too long may delay failover
3. Use parallel for speed - parallel mode is faster for ring groups
4. Use sequential for priority - sequential mode respects order and only creates channels as needed
5. Use balancing for distribution - balancing mode ensures even load distribution across destinations
6. Handle cleanup - if you need to hang up the answered channel, do it explicitly (cleanup of unanswered channels is automatic)

## Related

- [Load Balancer]({{< relref "load-balancer.md" >}}) - Learn about load balancer backends
- [Channel Abstraction]({{< relref "../channel.md" >}}) - Learn about channel creation and management
- [Group Call Example]({{< relref "../../Examples/group-call.md" >}}) - See a complete example implementation
