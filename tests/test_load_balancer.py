from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from genesis import InMemoryLoadBalancer, RedisLoadBalancer


@pytest.mark.asyncio
async def test_in_memory_load_balancer_increment_decrement():
    """Test increment and decrement operations."""
    lb = InMemoryLoadBalancer()

    assert await lb.get_count("user/1001") == 0

    await lb.increment("user/1001")
    assert await lb.get_count("user/1001") == 1

    await lb.increment("user/1001")
    assert await lb.get_count("user/1001") == 2

    await lb.decrement("user/1001")
    assert await lb.get_count("user/1001") == 1

    await lb.decrement("user/1001")
    assert await lb.get_count("user/1001") == 0

    await lb.decrement("user/1001")
    assert await lb.get_count("user/1001") == 0


@pytest.mark.asyncio
async def test_in_memory_load_balancer_get_least_loaded():
    """Test getting least loaded destination."""
    lb = InMemoryLoadBalancer()

    destinations = ["user/1001", "user/1002", "user/1003"]

    least = await lb.get_least_loaded(destinations)
    assert least == "user/1001"

    await lb.increment("user/1001")
    least = await lb.get_least_loaded(destinations)
    assert least in ["user/1002", "user/1003"]

    await lb.increment("user/1002")
    least = await lb.get_least_loaded(destinations)
    assert least == "user/1003"

    await lb.increment("user/1003")
    least = await lb.get_least_loaded(destinations)
    assert least == "user/1001"


@pytest.mark.asyncio
async def test_in_memory_load_balancer_empty_list():
    """Test with empty destination list."""
    lb = InMemoryLoadBalancer()

    least = await lb.get_least_loaded([])
    assert least is None


@pytest.mark.asyncio
async def test_in_memory_load_balancer_cleanup():
    """Test that decrementing to zero removes the key."""
    lb = InMemoryLoadBalancer()

    await lb.increment("user/1001")
    assert await lb.get_count("user/1001") == 1

    await lb.decrement("user/1001")
    assert await lb.get_count("user/1001") == 0


@pytest.mark.asyncio
async def test_redis_load_balancer_increment():
    """Test Redis load balancer increment operation."""
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock(return_value=1)

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        await lb.increment("user/1001")

        redis_client.incr.assert_called_once_with("genesis:lb:user/1001")


@pytest.mark.asyncio
async def test_redis_load_balancer_increment_custom_prefix():
    """Test Redis load balancer with custom key prefix."""
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock(return_value=1)

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer(key_prefix="custom:lb:")

        await lb.increment("user/1001")

        redis_client.incr.assert_called_once_with("custom:lb:user/1001")


@pytest.mark.asyncio
async def test_redis_load_balancer_decrement():
    """Test Redis load balancer decrement operation."""
    redis_client = AsyncMock()
    redis_client.decr = AsyncMock(return_value=0)
    redis_client.delete = AsyncMock(return_value=1)

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        await lb.decrement("user/1001")

        redis_client.decr.assert_called_once_with("genesis:lb:user/1001")
        redis_client.delete.assert_called_once_with("genesis:lb:user/1001")


@pytest.mark.asyncio
async def test_redis_load_balancer_decrement_no_cleanup():
    """Test Redis load balancer decrement when count > 0."""
    redis_client = AsyncMock()
    redis_client.decr = AsyncMock(return_value=1)
    redis_client.delete = AsyncMock()

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        await lb.decrement("user/1001")

        redis_client.decr.assert_called_once_with("genesis:lb:user/1001")
        redis_client.delete.assert_not_called()


@pytest.mark.asyncio
async def test_redis_load_balancer_get_count():
    """Test Redis load balancer get_count operation."""
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=b"5")

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        count = await lb.get_count("user/1001")

        assert count == 5
        redis_client.get.assert_called_once_with("genesis:lb:user/1001")


@pytest.mark.asyncio
async def test_redis_load_balancer_get_count_none():
    """Test Redis load balancer get_count when key doesn't exist."""
    redis_client = AsyncMock()
    redis_client.get = AsyncMock(return_value=None)

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        count = await lb.get_count("user/1001")

        assert count == 0
        redis_client.get.assert_called_once_with("genesis:lb:user/1001")


@pytest.mark.asyncio
async def test_redis_load_balancer_get_least_loaded():
    """Test Redis load balancer get_least_loaded operation."""
    redis_client = AsyncMock()
    redis_client.mget = AsyncMock(return_value=[b"2", b"1", b"3"])

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        destinations = ["user/1001", "user/1002", "user/1003"]
        least = await lb.get_least_loaded(destinations)

        assert least == "user/1002"
        redis_client.mget.assert_called_once_with(
            ["genesis:lb:user/1001", "genesis:lb:user/1002", "genesis:lb:user/1003"]
        )


@pytest.mark.asyncio
async def test_redis_load_balancer_get_least_loaded_with_none():
    """Test Redis load balancer get_least_loaded with None values."""
    redis_client = AsyncMock()
    redis_client.mget = AsyncMock(return_value=[b"2", None, None])

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        destinations = ["user/1001", "user/1002", "user/1003"]
        least = await lb.get_least_loaded(destinations)

        assert least in ["user/1002", "user/1003"]


@pytest.mark.asyncio
async def test_redis_load_balancer_get_least_loaded_empty_list():
    """Test Redis load balancer get_least_loaded with empty list."""
    redis_client = AsyncMock()

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        least = await lb.get_least_loaded([])

        assert least is None
        redis_client.mget.assert_not_called()


@pytest.mark.asyncio
async def test_redis_load_balancer_get_least_loaded_same_load():
    """Test Redis load balancer get_least_loaded when all have same load."""
    redis_client = AsyncMock()
    redis_client.mget = AsyncMock(return_value=[b"1", b"1", b"1"])

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        destinations = ["user/1001", "user/1002", "user/1003"]
        least = await lb.get_least_loaded(destinations)

        assert least == "user/1001"


@pytest.mark.asyncio
async def test_redis_load_balancer_connection_failure():
    """Test Redis load balancer raises on connection failures."""
    with patch(
        "genesis.group.load_balancer._create_redis_client",
        side_effect=Exception("Connection failed"),
    ):
        lb = RedisLoadBalancer()

        with pytest.raises(Exception, match="Connection failed"):
            await lb.increment("user/1001")

        with pytest.raises(Exception, match="Connection failed"):
            await lb.decrement("user/1001")

        with pytest.raises(Exception, match="Connection failed"):
            await lb.get_count("user/1001")

        with pytest.raises(Exception, match="Connection failed"):
            await lb.get_least_loaded(["user/1001", "user/1002"])


@pytest.mark.asyncio
async def test_redis_load_balancer_operation_failure():
    """Test Redis load balancer raises on operation failures."""
    redis_client = AsyncMock()
    redis_client.incr = AsyncMock(side_effect=Exception("Operation failed"))
    redis_client.decr = AsyncMock(side_effect=Exception("Operation failed"))
    redis_client.get = AsyncMock(side_effect=Exception("Operation failed"))
    redis_client.mget = AsyncMock(side_effect=Exception("Operation failed"))

    with patch(
        "genesis.group.load_balancer._create_redis_client", return_value=redis_client
    ):
        lb = RedisLoadBalancer()

        with pytest.raises(Exception, match="Operation failed"):
            await lb.increment("user/1001")

        with pytest.raises(Exception, match="Operation failed"):
            await lb.decrement("user/1001")

        with pytest.raises(Exception, match="Operation failed"):
            await lb.get_count("user/1001")

        with pytest.raises(Exception, match="Operation failed"):
            await lb.get_least_loaded(["user/1001", "user/1002"])
