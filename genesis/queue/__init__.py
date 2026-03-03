"""
Genesis queue
-------------

FIFO queue with concurrency limit per queue_id. Context-manager and
semaphore-like API; backends: in-memory (single process) or Redis (scalable).
"""

from genesis.exceptions import QueueTimeoutError
from genesis.queue.backends import InMemoryBackend, QueueBackend
from genesis.queue.core import Queue, QueueSemaphore, QueueSlot
from genesis.queue.redis_backend import RedisBackend

__all__ = [
    "Queue",
    "QueueBackend",
    "QueueSemaphore",
    "QueueSlot",
    "QueueTimeoutError",
    "InMemoryBackend",
    "RedisBackend",
]
