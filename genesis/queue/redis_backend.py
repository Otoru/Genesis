"""
Genesis queue Redis backend
---------------------------

Redis-backed queue for multi-process / horizontal scaling.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import redis.asyncio as redis

from genesis.exceptions import QueueTimeoutError
from genesis.queue.backends import QueueBackend

# Lua: try to acquire if we're at head and slots available. Keys: waiting_list, in_use_key. Args: item_id, max_concurrent.
SCRIPT_ACQUIRE = """
local head = redis.call('LINDEX', KEYS[1], 0)
if head == ARGV[1] then
  local in_use = tonumber(redis.call('GET', KEYS[2]) or '0')
  if in_use < tonumber(ARGV[2]) then
    redis.call('LPOP', KEYS[1])
    redis.call('INCR', KEYS[2])
    return 1
  end
end
return 0
"""


class RedisBackend:
    """
    Redis-backed queue backend.

    Uses a list for FIFO order and a counter for in-use slots per queue_id.
    Suitable for horizontal scaling (multiple app instances).
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379",
        key_prefix: str = "genesis:queue:",
    ) -> None:
        self._url = url
        self._prefix = key_prefix
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            self._client = await redis.from_url(self._url)
        return self._client

    def _waiting_key(self, queue_id: str) -> str:
        return f"{self._prefix}{queue_id}:waiting"

    def _in_use_key(self, queue_id: str) -> str:
        return f"{self._prefix}{queue_id}:in_use"

    def _channel(self, queue_id: str) -> str:
        return f"{self._prefix}{queue_id}:release"

    async def enqueue(self, queue_id: str, item_id: str) -> None:
        """Add item_id to the tail of the queue."""
        client = await self._get_client()
        key = self._waiting_key(queue_id)
        await client.rpush(key, item_id)

    async def _try_acquire(
        self,
        client: Any,
        waiting_key: str,
        in_use_key: str,
        item_id: str,
        max_concurrent: int,
    ) -> bool:
        """Try to acquire a slot; returns True if acquired."""
        try:
            script = client.register_script(SCRIPT_ACQUIRE)
            got = await script(
                keys=[waiting_key, in_use_key],
                args=[item_id, str(max_concurrent)],
            )
            return bool(got)
        except AttributeError:
            pass
        head = await client.lindex(waiting_key, 0)
        if head is not None:
            head = head.decode("utf-8") if isinstance(head, bytes) else head
        in_use = int(await client.get(in_use_key) or 0)
        if head == item_id and in_use < max_concurrent:
            await client.lpop(waiting_key)
            await client.incr(in_use_key)
            return True
        return False

    async def _wait_for_release_signal(self, client: Any, channel: str) -> None:
        """Block until a message is published on channel or timeout."""
        sub = client.pubsub()
        await sub.subscribe(channel)
        try:
            async for msg in sub.listen():
                if msg.get("type") == "message":
                    return
                await asyncio.sleep(0)
        finally:
            await sub.unsubscribe(channel)
            await sub.close()

    async def wait_and_acquire(
        self,
        queue_id: str,
        item_id: str,
        max_concurrent: int,
        timeout: Optional[float] = None,
    ) -> None:
        """
        Block until this item is at the head and a slot is free, then pop head and acquire.
        If timeout (seconds) expires, remove item from waiting list and raise QueueTimeoutError.
        """
        client = await self._get_client()
        waiting_key = self._waiting_key(queue_id)
        in_use_key = self._in_use_key(queue_id)
        channel = self._channel(queue_id)
        deadline = time.monotonic() + timeout if timeout is not None else None

        while True:
            if await self._try_acquire(
                client, waiting_key, in_use_key, item_id, max_concurrent
            ):
                return
            wait_timeout = 1.0
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await client.lrem(waiting_key, 1, item_id)
                    raise QueueTimeoutError()
                wait_timeout = min(1.0, remaining)
            try:
                await asyncio.wait_for(
                    self._wait_for_release_signal(client, channel),
                    timeout=wait_timeout,
                )
            except asyncio.TimeoutError:
                if deadline is not None and time.monotonic() >= deadline:
                    await client.lrem(waiting_key, 1, item_id)
                    raise QueueTimeoutError()
                # retry loop

    async def release(self, queue_id: str) -> None:
        """Release one slot for the queue."""
        client = await self._get_client()
        in_use_key = self._in_use_key(queue_id)
        channel = self._channel(queue_id)
        await client.decr(in_use_key)
        await client.publish(channel, "1")
