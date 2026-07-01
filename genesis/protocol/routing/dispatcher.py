"""
Event Dispatcher
----------------

Helper for dispatching events to handlers asynchronously.
"""

from asyncio import Task, create_task, to_thread, iscoroutinefunction
from typing import List, Optional, Set, Any

from genesis.observability import logger
from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import consumer_handlers_counter, safe_add
from genesis.types import EventHandler


def _handler_done_callback(task_set: Set[Task[Any]], task: Task[Any]) -> None:
    task_set.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error(f"Unhandled exception in event handler: {task.exception()}")


def dispatch_to_handlers(
    handlers: List[EventHandler],
    event: ESLEvent,
    task_set: Optional[Set[Task[Any]]] = None,
) -> None:
    """Dispatch event to all handlers asynchronously.

    Args:
        handlers: List of event handlers
        event: The ESL event to dispatch
        task_set: Optional set to track live tasks (prevents GC and logs exceptions)
    """
    event_name = event.get("Event-Name", "UNKNOWN")
    if isinstance(event_name, list):
        event_name = event_name[0] if event_name else "UNKNOWN"
    for handler in handlers:
        safe_add(
            consumer_handlers_counter,
            1,
            attributes={"event.name": str(event_name)},
        )
        if iscoroutinefunction(handler):
            task = create_task(handler(event))
        else:
            task = create_task(to_thread(handler, event))

        if task_set is not None:
            task_set.add(task)
            task.add_done_callback(lambda t: _handler_done_callback(task_set, t))
