"""Tests for running Genesis without the optional redis extra."""

import subprocess
import sys
import textwrap


def _run_without_redis(code: str) -> subprocess.CompletedProcess[str]:
    """Run code in a fresh interpreter where `import redis` fails."""
    script = "import sys\nsys.modules['redis'] = None\n" + textwrap.dedent(code)
    return subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )


def test_import_genesis_without_redis():
    """Genesis imports cleanly when redis is not installed."""
    result = _run_without_redis("""
        import genesis
        from genesis import RedisBackend, RedisLoadBalancer
        RedisBackend()
        RedisLoadBalancer()
        """)
    assert result.returncode == 0, result.stderr


def test_redis_backend_without_redis_points_to_extra():
    """RedisBackend explains how to install the extra when redis is missing."""
    result = _run_without_redis("""
        import asyncio
        from genesis import RedisBackend
        try:
            asyncio.run(RedisBackend().enqueue("q1", "item1"))
        except ImportError as exc:
            print(exc)
        """)
    assert result.returncode == 0, result.stderr
    assert "pip install genesis[redis]" in result.stdout


def test_redis_load_balancer_without_redis_points_to_extra():
    """RedisLoadBalancer explains how to install the extra when redis is missing."""
    result = _run_without_redis("""
        import asyncio
        from genesis import RedisLoadBalancer
        try:
            asyncio.run(RedisLoadBalancer().increment("user/1001"))
        except ImportError as exc:
            print(exc)
        """)
    assert result.returncode == 0, result.stderr
    assert "pip install genesis[redis]" in result.stdout
