"""
Composite Routing Strategy
---------------------------

Chains multiple routing strategies together, stopping at first match.
"""

from typing import List, Tuple

from genesis.protocol.routing.base import RoutingStrategy
from genesis.protocol.parser import ESLEvent
from genesis.types import EventHandler


class CompositeRoutingStrategy(RoutingStrategy):
    """Composite strategy that chains multiple strategies."""

    def __init__(self, strategies: List[RoutingStrategy]):
        """Initialize with list of strategies.

        Args:
            strategies: List of strategies to try in order
        """
        self.strategies = strategies

    def get_event_name(self, event: ESLEvent) -> str | None:
        """Extract event name from ESL event."""
        from typing import cast

        identifier = cast(str | None, event.get("Event-Name", None))
        if identifier == "CUSTOM":
            return cast(str | None, event.get("Event-Subclass", None))
        return identifier

    async def route(self, event: ESLEvent) -> Tuple[List[EventHandler], bool]:
        """Try each strategy in order until one handles the event.

        Returns:
            (handlers, should_stop) from first strategy that returns handlers
        """
        for strategy in self.strategies:
            handlers, should_stop = await strategy.route(event)

            if handlers:
                return (handlers, should_stop)

            if should_stop:
                # Strategy explicitly stopped routing chain
                return ([], True)

        return ([], False)
