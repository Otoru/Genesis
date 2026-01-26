"""
Genesis group
------------

Abstraction for managing simultaneous call groups (ring groups).
"""

from __future__ import annotations

from typing import Optional, Dict, List, Literal
from enum import Enum
import asyncio
import time

from opentelemetry import trace, metrics

from genesis.protocol import Protocol
from genesis.channel import Channel
from genesis.types import ChannelState, HangupCause
from genesis.exceptions import TimeoutError
from genesis.group.load_balancer import LoadBalancerBackend

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Ring group metrics
ring_group_operations_counter = meter.create_counter(
    "genesis.ring_group.operations",
    description="Number of ring group operations",
    unit="1",
)

ring_group_operation_duration = meter.create_histogram(
    "genesis.ring_group.operation.duration",
    description="Duration of ring group operations",
    unit="s",
)

ring_group_results_counter = meter.create_counter(
    "genesis.ring_group.results",
    description="Ring group operation results",
    unit="1",
)


class RingMode(str, Enum):
    """Ring mode for group calls."""

    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    BALANCING = "balancing"


class RingGroup:
    """
    RingGroup class
    ---------------

    Factory for managing ring groups with parallel, sequential, or balancing calling.

    Example:
        # With Inbound protocol
        async with Inbound(host, port, password) as client:
            answered = await RingGroup.ring(
                client, ["user/1001", "user/1002"], RingMode.PARALLEL
            )

        # With load balancing
        async with Inbound(host, port, password) as client:
            lb = InMemoryLoadBalancer()
            answered = await RingGroup.ring(
                client, ["user/1001", "user/1002"], RingMode.BALANCING, balancer=lb
            )

        # With Session (outbound) protocol
        async def handler(session):
            answered = await RingGroup.ring(
                session, ["user/1001", "user/1002"], RingMode.PARALLEL
            )
            if answered:
                await session.channel.bridge(answered)
    """

    @staticmethod
    async def ring(
        protocol: Protocol,
        group: List[str],
        mode: RingMode = RingMode.PARALLEL,
        timeout: float = 30.0,
        variables: Optional[Dict[str, str]] = None,
        balancer: Optional[LoadBalancerBackend] = None,
    ) -> Optional[Channel]:
        """
        Ring a group of destinations and return the first one that answers.

        Args:
            protocol: Protocol instance (Inbound or Session)
            group: List of destinations to call
            mode: Ring mode (default: PARALLEL)
              - PARALLEL: Call all destinations simultaneously
              - SEQUENTIAL: Call destinations one at a time
              - BALANCING: Call all destinations simultaneously with load balancing
            timeout: Maximum time to wait for any callee to answer
            variables: Optional variables for callee channel creation
            balancer: Required for BALANCING mode, ignored for other modes

        Returns:
            Channel that answered first, or None if none answered within timeout
        """
        start_time = time.time()

        with tracer.start_as_current_span(
            "ring_group.ring",
            attributes={
                "ring_group.mode": mode.value,
                "ring_group.size": len(group),
                "ring_group.timeout": timeout,
                "ring_group.has_balancer": str(
                    balancer is not None and mode == RingMode.BALANCING
                ),
                "ring_group.has_variables": str(variables is not None),
            },
        ) as span:
            try:
                if mode == RingMode.PARALLEL:
                    answered = await RingGroup._ring_parallel(
                        protocol, group, timeout, variables or {}
                    )
                elif mode == RingMode.SEQUENTIAL:
                    answered = await RingGroup._ring_sequential(
                        protocol, group, timeout, variables or {}
                    )
                elif mode == RingMode.BALANCING:
                    if not balancer:
                        raise ValueError("Load balancer is required for BALANCING mode")
                    answered = await RingGroup._ring_balancing(
                        protocol, group, timeout, variables or {}, balancer
                    )
                else:
                    raise ValueError(f"Unknown ring mode: {mode}")

                duration = time.time() - start_time
                span.set_attribute(
                    "ring_group.result", "answered" if answered else "no_answer"
                )
                span.set_attribute("ring_group.duration", duration)
                if answered:
                    span.set_attribute(
                        "ring_group.answered_uuid", answered.uuid or "unknown"
                    )
                    span.set_attribute(
                        "ring_group.answered_dial_path", answered.dial_path
                    )

                # Record metrics
                ring_group_operations_counter.add(
                    1,
                    attributes={
                        "mode": mode.value,
                        "has_balancer": str(
                            balancer is not None and mode == RingMode.BALANCING
                        ),
                    },
                )
                ring_group_operation_duration.record(
                    duration,
                    attributes={
                        "mode": mode.value,
                        "has_balancer": str(
                            balancer is not None and mode == RingMode.BALANCING
                        ),
                    },
                )
                ring_group_results_counter.add(
                    1,
                    attributes={
                        "mode": mode.value,
                        "result": "answered" if answered else "no_answer",
                        "has_balancer": str(
                            balancer is not None and mode == RingMode.BALANCING
                        ),
                    },
                )

                return answered

            except Exception as e:
                duration = time.time() - start_time
                span.set_attribute("ring_group.result", "error")
                span.set_attribute("ring_group.error", str(e))
                span.set_attribute("ring_group.duration", duration)
                span.record_exception(e)

                ring_group_results_counter.add(
                    1,
                    attributes={
                        "mode": mode.value,
                        "result": "error",
                        "error": type(e).__name__,
                        "has_balancer": str(
                            balancer is not None and mode == RingMode.BALANCING
                        ),
                    },
                )
                raise

    @staticmethod
    async def _ring_parallel(
        protocol: Protocol,
        group: List[str],
        timeout: float,
        variables: Dict[str, str],
    ) -> Optional[Channel]:
        """Ring all destinations simultaneously, return first to answer."""

        # Originate all callees simultaneously
        callees: List[Channel] = []
        callee_map: Dict[Channel, str] = {}
        for callee in group:
            ch = await Channel.create(protocol, callee, variables=variables)
            callees.append(ch)
            callee_map[ch] = callee

        # Create tasks to wait for callees to answer
        # Use a longer timeout for individual waits to ensure they don't timeout
        # before the global timeout
        tasks: Dict[asyncio.Task, Channel] = {}
        for ch in callees:
            task = asyncio.create_task(
                ch.wait(ChannelState.EXECUTE, timeout=timeout * 2)
            )
            tasks[task] = ch

        answered: Optional[Channel] = None

        async def cleanup() -> None:
            """Cleanup function to ensure proper cleanup on timeout."""
            nonlocal answered

            # Cancel all pending tasks
            for task in tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, TimeoutError):
                        pass

            # Hang up all channels that didn't answer
            await RingGroup._cleanup_unanswered(callees, answered)

        try:
            # Wait for the first callee to answer with global timeout
            done, pending = await asyncio.wait(
                tasks.keys(), return_when=asyncio.FIRST_COMPLETED, timeout=timeout
            )

            # If no callee answered (timeout), cleanup and return None
            if not done:
                await cleanup()
                return None

            # Get the first callee to answer
            answered_task = done.pop()
            answered = tasks[answered_task]

            # Wait for the task to complete (may raise if it failed)
            try:
                await answered_task
            except TimeoutError:
                # Task completed but with timeout
                answered = None
                await cleanup()
                return None

            # Cancel pending tasks and hang up channels that didn't answer
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, TimeoutError):
                    pass

            # Hang up channels that didn't answer
            await RingGroup._cleanup_unanswered(callees, answered)

            return answered

        except asyncio.TimeoutError:
            # Global timeout expired - cleanup all channels
            await cleanup()
            return None
        except Exception:
            # On any error, clean up all channels
            await cleanup()
            raise

    @staticmethod
    async def _ring_sequential(
        protocol: Protocol,
        group: List[str],
        timeout: float,
        variables: Dict[str, str],
    ) -> Optional[Channel]:
        """Ring destinations one at a time, return first to answer."""

        for callee in group:
            ch = await Channel.create(protocol, callee, variables=variables)
            try:
                await ch.wait(ChannelState.EXECUTE, timeout=timeout)
                return ch
            except TimeoutError:
                if ch.state < ChannelState.HANGUP:
                    try:
                        await ch.hangup("NORMAL_CLEARING")
                    except Exception:
                        pass
                continue

        return None

    @staticmethod
    async def _ring_balancing(
        protocol: Protocol,
        group: List[str],
        timeout: float,
        variables: Dict[str, str],
        balancer: LoadBalancerBackend,
    ) -> Optional[Channel]:
        """Ring destinations sequentially using load balancing, return first to answer."""

        remaining = list(group)
        while remaining:
            least_loaded = await balancer.get_least_loaded(remaining)
            if not least_loaded:
                least_loaded = remaining[0]

            await balancer.increment(least_loaded)

            ch = await Channel.create(protocol, least_loaded, variables=variables)
            try:
                await ch.wait(ChannelState.EXECUTE, timeout=timeout)
                await balancer.decrement(least_loaded)
                return ch
            except TimeoutError:
                await balancer.decrement(least_loaded)
                if ch.state < ChannelState.HANGUP:
                    try:
                        await ch.hangup("NORMAL_CLEARING")
                    except Exception:
                        pass
                remaining.remove(least_loaded)
                continue

        return None

    @staticmethod
    async def _cleanup_unanswered(
        callees: List[Channel], answered: Optional[Channel]
    ) -> None:
        """Hang up all callee channels that didn't answer."""
        for ch in callees:
            if ch == answered:
                continue
            if ch.state >= ChannelState.HANGUP:
                continue
            try:
                await ch.hangup("NORMAL_CLEARING")
            except Exception:
                pass
