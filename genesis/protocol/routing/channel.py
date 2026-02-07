"""
Channel Routing Strategy
-------------------------

O(1) routing strategy for channel-specific events using UUID-based lookup.
"""

from typing import Dict, List, Tuple

from genesis.protocol.routing.base import RoutingStrategy
from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import channel_routing_counter
from genesis.logger import logger
from genesis.types import EventHandler


class ChannelRoutingStrategy(RoutingStrategy):
    """O(1) channel-specific routing using Unique-ID."""

    def __init__(self, channel_registry: Dict[str, List[EventHandler]]):
        """Initialize with channel registry.

        Args:
            channel_registry: Dict mapping "uuid:event_name" to handlers
        """
        self.channel_registry = channel_registry

    def get_event_name(self, event: ESLEvent) -> str | None:
        """Extract event name from ESL event."""
        from typing import cast

        identifier = cast(str | None, event.get("Event-Name", None))
        if identifier == "CUSTOM":
            return cast(str | None, event.get("Event-Subclass", None))
        return identifier

    async def route(self, event: ESLEvent) -> Tuple[List[EventHandler], bool]:
        """Route event using O(1) channel lookup.

        Returns:
            (handlers, True) if channel handlers found, ([], False) otherwise
        """
        uuid = event.get("Unique-ID", None)
        name = self.get_event_name(event)

        if not uuid or not name:
            return ([], False)

        channel_key = f"{uuid}:{name}"
        handlers = self.channel_registry.get(channel_key, [])

        if handlers:
            # Record O(1) routing metric
            try:
                channel_routing_counter.add(1, attributes={"event_name": name})
            except Exception:
                pass

            logger.trace(f"O(1) routing for '{channel_key}' ({len(handlers)} handlers)")
            return (handlers, True)  # Stop routing chain

        return ([], False)  # Continue to next strategy
