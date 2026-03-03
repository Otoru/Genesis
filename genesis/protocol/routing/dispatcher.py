"""
Event Dispatcher
----------------

Helper for dispatching events to handlers asynchronously.
"""

from asyncio import create_task, to_thread, iscoroutinefunction
from typing import List

from genesis.protocol.parser import ESLEvent
from genesis.types import EventHandler


def dispatch_to_handlers(handlers: List[EventHandler], event: ESLEvent) -> None:
    """Dispatch event to all handlers asynchronously (fire-and-forget tasks).

    Args:
        handlers: List of event handlers
        event: The ESL event to dispatch
    """
    _tasks: list = []
    for handler in handlers:
        if iscoroutinefunction(handler):
            _tasks.append(create_task(handler(event)))
        else:
            _tasks.append(create_task(to_thread(handler, event)))
