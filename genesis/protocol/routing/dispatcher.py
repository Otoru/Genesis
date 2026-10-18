"""
Event Dispatcher
----------------

Helper for dispatching events to handlers asynchronously.
"""

from asyncio import Task, create_task, iscoroutine, iscoroutinefunction, to_thread
from typing import List, Optional, Set, Any

from genesis.observability import logger
from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import consumer_handlers_counter, safe_add
from genesis.types import EventHandler

_RUN_ON_LOOP = "_genesis_run_on_loop"


def run_on_loop(handler: EventHandler) -> EventHandler:
    """Run this handler on the event-loop thread.

    Synchronous handlers otherwise go through ``to_thread``. Callbacks that
    complete an asyncio future have to stay on the loop that owns it.
    """
    setattr(handler, _RUN_ON_LOOP, True)
    return handler


async def _invoke_on_loop(handler: EventHandler, event: ESLEvent) -> None:
    """Call ``handler`` on the loop and await it when it returns a coroutine."""
    outcome = handler(event)
    if iscoroutine(outcome):
        await outcome


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
        elif getattr(handler, _RUN_ON_LOOP, False):
            task = create_task(_invoke_on_loop(handler, event))
        else:
            task = create_task(to_thread(handler, event))

        if task_set is not None:
            task_set.add(task)
            task.add_done_callback(lambda t: _handler_done_callback(task_set, t))
