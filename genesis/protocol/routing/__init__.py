"""
Event Routing Strategies
=========================

Strategy Pattern implementation for flexible event routing in the Protocol.

Design Pattern: Strategy
-------------------------
The Strategy Pattern allows selecting routing algorithms at runtime. Each strategy
encapsulates a specific routing behavior, making it easy to add new routing types
without modifying existing code.

Architecture
------------
- **RoutingStrategy (ABC)**: Base interface for all routing strategies
- **ChannelRoutingStrategy**: O(1) routing using UUID-based lookup
- **GlobalRoutingStrategy**: O(N) routing using event name lookup
- **CompositeRoutingStrategy**: Chains multiple strategies together

Current Flow
------------
1. Event arrives in Protocol.consume()
2. CompositeRoutingStrategy tries ChannelRoutingStrategy first (O(1))
3. If no channel handlers found, falls back to GlobalRoutingStrategy (O(N))
4. Handlers are dispatched asynchronously via dispatch_to_handlers()
"""

from genesis.protocol.routing.base import RoutingStrategy
from genesis.protocol.routing.channel import ChannelRoutingStrategy
from genesis.protocol.routing.global_ import GlobalRoutingStrategy
from genesis.protocol.routing.composite import CompositeRoutingStrategy
from genesis.protocol.routing.dispatcher import dispatch_to_handlers

__all__ = [
    "RoutingStrategy",
    "ChannelRoutingStrategy",
    "GlobalRoutingStrategy",
    "CompositeRoutingStrategy",
    "dispatch_to_handlers",
]
