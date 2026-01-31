"""
Routing Strategy Base Class
----------------------------

Abstract base class for event routing strategies.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple

from genesis.protocol.parser import ESLEvent
from genesis.types import EventHandler


class RoutingStrategy(ABC):
    """Abstract base class for event routing strategies."""

    @abstractmethod
    def get_event_name(self, event: ESLEvent) -> str | None:
        """Extract event name from ESL event.

        Args:
            event: The ESL event

        Returns:
            Event name or None if not found
        """
        from typing import cast

        identifier = cast(str | None, event.get("Event-Name", None))
        if identifier == "CUSTOM":
            return cast(str | None, event.get("Event-Subclass", None))
        return identifier

    @abstractmethod
    async def route(self, event: ESLEvent) -> Tuple[List[EventHandler], bool]:
        """Route event to appropriate handlers.

        Args:
            event: The ESL event to route

        Returns:
            Tuple of (handlers_list, should_stop_routing)
            - handlers_list: List of handlers that should receive this event
            - should_stop_routing: True if routing chain should stop (event was handled)
        """
        pass
