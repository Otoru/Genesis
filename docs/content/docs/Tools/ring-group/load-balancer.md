---
title: Load Balancer
weight: 31
---

Load balancing ensures calls are distributed evenly across your destinations. The load balancer determines which destination to try first based on current load, prioritizing less busy destinations. Destinations are called sequentially (one at a time) in order of least to most loaded, ensuring even distribution when using the same balancer across multiple groups.

## Why Use Load Balancing?

Without load balancing, if you ring `["user/1001", "user/1002", "user/1003"]` in multiple groups, `user/1001` will always be tried first in each group and may become overloaded while others remain idle.

With load balancing, the system tracks how many active calls each destination is handling and tries destinations in order from least to most loaded. This ensures that less busy destinations are contacted first, preventing specific destinations from being overloaded when using the same balancer instance across multiple groups.

## Strategies

Choose the load balancer backend based on your deployment architecture:

### Single Instance

If you're running a single instance of your application, use `InMemoryLoadBalancer`:

```python
from genesis import Inbound, RingGroup, RingMode, InMemoryLoadBalancer

async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
    # Create load balancer once and reuse it
    balancer = InMemoryLoadBalancer()
    
    # Each call will be routed to the least busy agent
    answered = await RingGroup.ring(
        client,
        ["user/1001", "user/1002", "user/1003"],
        RingMode.BALANCING,
        balancer=balancer
    )
```

The load balancer automatically tracks active calls and distributes them evenly. Create it once and reuse it across multiple ring operations. If the same balancer instance is used with different groups, destinations that appear in multiple groups will have their load tracked correctly.

### Multiple Instances

If you're running multiple instances of your application, use `RedisLoadBalancer` so all instances can coordinate:

```python
from genesis import Inbound, RingGroup, RingMode, RedisLoadBalancer

# Create load balancer with Redis URL
# The redis package is automatically installed if needed
balancer = RedisLoadBalancer("redis://localhost:6379")

async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
    answered = await RingGroup.ring(
        client,
        ["user/1001", "user/1002", "user/1003"],
        RingMode.BALANCING,
        balancer=balancer
    )
```

All application instances share the same Redis connection, so they coordinate load distribution across the entire cluster. The redis package is automatically installed when needed.

## Custom Redis Key Prefix

If you need to avoid key collisions in Redis, customize the prefix:

```python
balancer = RedisLoadBalancer("redis://localhost:6379", key_prefix="myapp:lb:")
```

## Best Practices

1. Create the load balancer instance once and reuse it across all ring operations

2. Use `InMemoryLoadBalancer` for single-instance deployments, `RedisLoadBalancer` when running multiple instances

3. If Redis becomes unavailable, `RedisLoadBalancer` will raise exceptions. Ensure your application handles these errors appropriately

## Related

- [Ring Group]({{< relref "_index.md" >}}) - Learn about ring groups
- [Observability]({{< relref "../../observability.md" >}}) - Monitor load balancer metrics and distribution
- [Group Call Example]({{< relref "../../Examples/group-call.md" >}}) - See a complete example
