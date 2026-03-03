---
title: Backends
weight: 41
---

Backends store queue state (FIFO order and concurrency). Choose the backend based on whether you run a single instance or multiple instances of your application.

## Single Instance

If you run a single process, use the default in-memory backend:

```python
from genesis import Queue

queue = Queue()  # InMemoryBackend by default
```

- State lives in process memory
- No extra dependencies
- Omit the backend for simplicity

## Multiple Instances

If you run multiple instances (horizontal scaling), pass `RedisBackend` so all instances share the same queue state:

```python
from genesis import Queue
from genesis.queue import RedisBackend

queue = Queue(RedisBackend(url="redis://localhost:6379"))

async with queue.slot("sales", item_id=session.uuid):
    # ...
```

- State lives in Redis (list + counter per queue, pub/sub to wake waiters)
- Each instance enqueues its own call and waits until it is that call's turn; the **process that holds the ESL session** must be the one that runs the handler. Redis only stores order and concurrency.
- Optional **timeout** on `queue.slot()` / `queue.semaphore()` is supported by both backends; when it expires, the item is removed and :exc:`genesis.exceptions.QueueTimeoutError` is raised.

## Custom Redis Key Prefix

To avoid key collisions in Redis, set a custom prefix:

```python
backend = RedisBackend(
    url="redis://localhost:6379",
    key_prefix="myapp:queue:"
)
queue = Queue(backend)
```

## Parameters

**`Queue(backend=None)`**

- `backend`: Backend to use (FIFO + concurrency state). Default: `InMemoryBackend`, so `Queue()` is enough for single-process use.

**`InMemoryBackend()`**

- No arguments

**`RedisBackend(url="redis://localhost:6379", key_prefix="genesis:queue:")`**

- `url`: Redis connection URL
- `key_prefix`: Prefix for Redis keys (default: `"genesis:queue:"`)

## Best Practices

1. Create the backend once and reuse the same `Queue` instance (e.g. at app startup)
2. Use `InMemoryBackend` for single-instance deployments, `RedisBackend` when running multiple instances
3. With Redis, pass `item_id=session.uuid` (or similar) when acquiring a slot so you can correlate metrics and traces across instances
4. If Redis becomes unavailable, `RedisBackend` will raise; ensure your application handles these errors

## Related

- [Queue]({{< relref "_index.md" >}}) - API and usage
- [Ring Group]({{< relref "../ring-group/_index.md" >}}) - Often used inside a queue slot
- [Observability / Metrics]({{< relref "../../Observability/metrics.md" >}}) - Queue metrics
