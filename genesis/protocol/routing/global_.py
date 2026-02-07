"""
Global Routing Strategy
------------------------

O(N) routing strategy for global event handlers.
"""

from typing import Dict, List, Tuple

from genesis.protocol.routing.base import RoutingStrategy
from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import global_routing_counter
from genesis.observability import logger
from genesis.types import EventHandler


class GlobalRoutingStrategy(RoutingStrategy):
    """O(N) global routing for events without channel-specific handlers."""

    def __init__(self, handlers: Dict[str, List[EventHandler]]):
        """Initialize with global handlers registry.

        Args:
            handlers: Dict mapping event names to handlers
        """
        self.handlers = handlers

    def get_event_name(self, event: ESLEvent) -> str | None:
        """Extract event name from ESL event."""
        from typing import cast

        identifier = cast(str | None, event.get("Event-Name", None))
        if identifier == "CUSTOM":
            return cast(str | None, event.get("Event-Subclass", None))
        return identifier

    async def route(self, event: ESLEvent) -> Tuple[List[EventHandler], bool]:
        """Route event using O(N) global handler lookup.

        Returns:
            (handlers, False) - never stops routing chain
        """
        name = self.get_event_name(event)

        if not name:
            return ([], False)

        # Record O(N) routing metric
        try:
            global_routing_counter.add(1, attributes={"event_name": name})
        except Exception:
            pass

        logger.trace(f"Global routing for '{name}'")

        # Get specific handlers for this event name
        specific = self.handlers.get(name, [])
        # Get wildcard handlers
        generic = self.handlers.get("*", [])

        return (specific + generic, False)  # Don't stop routing chain
