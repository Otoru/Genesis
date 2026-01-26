"""
Genesis load balancer
---------------------

Load balancing backends for ring groups.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Protocol, List, Optional, Any, Awaitable
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    try:
        import redis.asyncio as redis
    except ImportError:
        redis = None
else:
    try:
        import redis.asyncio as redis
    except ImportError:
        redis = None


async def _create_redis_client(url: str = "redis://localhost:6379") -> Any:
    """
    Create a Redis async client, installing redis package if needed.

    Internal helper function.

    Args:
        url: Redis connection URL (default: "redis://localhost:6379")

    Returns:
        Redis async client instance

    Raises:
        RuntimeError: If redis package cannot be installed or imported
    """
    # Import here to handle optional dependency
    try:
        import redis.asyncio as redis_module
    except ImportError:
        # Try to install redis automatically
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "redis>=5.0.0"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Re-import after installation
            import redis.asyncio as redis_module
        except (subprocess.CalledProcessError, ImportError):
            raise RuntimeError(
                "Redis package is required for RedisLoadBalancer. "
                "Install it with: pip install redis"
            )

    return await redis_module.from_url(url)


class LoadBalancerBackend(Protocol):
    """
    Protocol for load balancer backends.

    Implementations should track call counts per destination
    and provide methods to get the least loaded destination.
    """

    async def increment(self, destination: str) -> None:
        """Increment call count for a destination."""
        ...

    async def decrement(self, destination: str) -> None:
        """Decrement call count for a destination."""
        ...

    async def get_least_loaded(self, destinations: List[str]) -> Optional[str]:
        """
        Get the least loaded destination from the list.

        Returns None if all destinations are unavailable or list is empty.
        """
        ...

    async def get_count(self, destination: str) -> int:
        """Get current call count for a destination."""
        ...


class InMemoryLoadBalancer:
    """
    In-memory load balancer backend.

    Tracks call counts in memory. Suitable for single-instance deployments.
    """

    def __init__(self) -> None:
        """Initialize in-memory load balancer."""
        self._counts: dict[str, int] = {}

    async def increment(self, destination: str) -> None:
        """Increment call count for a destination."""
        self._counts[destination] = self._counts.get(destination, 0) + 1

    async def decrement(self, destination: str) -> None:
        """Decrement call count for a destination."""
        current = self._counts.get(destination, 0)
        if current > 0:
            self._counts[destination] = current - 1
            if self._counts[destination] == 0:
                del self._counts[destination]

    async def get_least_loaded(self, destinations: List[str]) -> Optional[str]:
        """Get the least loaded destination from the list."""
        if not destinations:
            return None

        # Get counts for all destinations
        counts = {dest: self._counts.get(dest, 0) for dest in destinations}

        # Find minimum count
        min_count = min(counts.values())

        # Return first destination with minimum count
        for dest in destinations:
            if counts[dest] == min_count:
                return dest

        return None

    async def get_count(self, destination: str) -> int:
        """Get current call count for a destination."""
        return self._counts.get(destination, 0)


class RedisClient(Protocol):
    """Protocol for Redis async client."""

    async def incr(self, key: str) -> int:
        """Increment a key and return the new value."""
        ...

    async def decr(self, key: str) -> int:
        """Decrement a key and return the new value."""
        ...

    async def delete(self, key: str) -> int:
        """Delete a key."""
        ...

    async def mget(self, keys: List[str]) -> List[Optional[bytes]]:
        """Get multiple keys."""
        ...

    async def get(self, key: str) -> Optional[bytes]:
        """Get a key."""
        ...


class RedisLoadBalancer:
    """
    Redis-based load balancer backend.

    Tracks call counts in Redis. Suitable for horizontal scaling.
    The redis package is automatically installed when needed.

    Args:
        url: Redis connection URL (default: "redis://localhost:6379")
        key_prefix: Prefix for Redis keys (default: "genesis:lb:")
    """

    def __init__(
        self, url: str = "redis://localhost:6379", key_prefix: str = "genesis:lb:"
    ) -> None:
        """
        Initialize Redis load balancer.

        Args:
            url: Redis connection URL
            key_prefix: Prefix for Redis keys
        """
        self.url = url
        self.prefix = key_prefix
        self._redis: Optional[Any] = None

    async def _get_redis(self) -> Any:
        """Get Redis client, creating it if needed."""
        if self._redis is None:
            self._redis = await _create_redis_client(self.url)
        return self._redis

    def _key(self, destination: str) -> str:
        """Get Redis key for a destination."""
        return f"{self.prefix}{destination}"

    async def increment(self, destination: str) -> None:
        """Increment call count for a destination."""
        redis_client = await self._get_redis()
        key = self._key(destination)
        try:
            await redis_client.incr(key)
        except Exception as e:
            # Reset connection to retry on next call
            self._redis = None
            raise

    async def decrement(self, destination: str) -> None:
        """Decrement call count for a destination."""
        redis_client = await self._get_redis()
        key = self._key(destination)
        try:
            count = await redis_client.decr(key)
            # Clean up if count reaches zero
            if count <= 0:
                await redis_client.delete(key)
        except Exception as e:
            # Reset connection to retry on next call
            self._redis = None
            raise

    async def get_least_loaded(self, destinations: List[str]) -> Optional[str]:
        """Get the least loaded destination from the list."""
        if not destinations:
            return None

        redis_client = await self._get_redis()
        try:
            # Get counts for all destinations
            keys = [self._key(dest) for dest in destinations]
            values = await redis_client.mget(keys)

            # Parse counts (None/Nonexistent keys become 0)
            counts = {
                dest: int(val) if val is not None else 0
                for dest, val in zip(destinations, values)
            }

            # Find minimum count
            min_count = min(counts.values())

            # Return first destination with minimum count
            for dest in destinations:
                if counts[dest] == min_count:
                    return dest

            return None
        except Exception as e:
            # Reset connection to retry on next call
            self._redis = None
            raise

    async def get_count(self, destination: str) -> int:
        """Get current call count for a destination."""
        redis_client = await self._get_redis()
        key = self._key(destination)
        try:
            value = await redis_client.get(key)
            return int(value) if value is not None else 0
        except Exception as e:
            # Reset connection to retry on next call
            self._redis = None
            raise
