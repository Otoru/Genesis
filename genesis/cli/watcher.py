import asyncio
import fnmatch
from pathlib import Path
from typing import Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEvent, FileSystemEventHandler


class EventHandler(FileSystemEventHandler):
    """
    Event handler
    -------------

    This class is responsible for handling the events from the filesystem.
    """

    def __init__(
        self, queue: asyncio.Queue, loop: asyncio.BaseEventLoop, *args, **kwargs
    ):
        self._loop = loop
        self._queue = queue
        super(*args, **kwargs)

    def on_any_event(self, event: FileSystemEvent) -> None:
        if fnmatch.fnmatch(event.src_path, "*.py"):
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)


class EventIterator(object):
    """ "
    Event iterator
    --------------

    This class is responsible for iterating over the events from the queue.
    """

    def __init__(
        self, queue: asyncio.Queue, loop: Optional[asyncio.BaseEventLoop] = None
    ):
        self.queue = queue

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.queue.get()
        if item is not None:
            return item


def factory(
    path: Path,
    queue: asyncio.Queue,
    loop: asyncio.BaseEventLoop,
    recursive: bool = True,
) -> Observer:
    """This function creates an observer instance and returns it."""
    handler = EventHandler(queue, loop)

    observer = Observer()
    observer.schedule(handler, str(path), recursive=recursive)

    return observer
