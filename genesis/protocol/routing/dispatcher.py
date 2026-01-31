"""
Event Dispatcher
----------------

Helper for dispatching events to handlers asynchronously.
"""

from asyncio import create_task, to_thread, iscoroutinefunction
from typing import List

from genesis.protocol.parser import ESLEvent
from genesis.types import EventHandler


async def dispatch_to_handlers(handlers: List[EventHandler], event: ESLEvent) -> None:
    """Dispatch event to all handlers asynchronously.

    Args:
        handlers: List of event handlers
        event: The ESL event to dispatch
    """
    for handler in handlers:
        if iscoroutinefunction(handler):
            create_task(handler(event))
        else:
            create_task(to_thread(handler, event))
