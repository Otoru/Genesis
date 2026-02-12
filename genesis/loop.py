"""
Event loop utilities.

Provides optional uvloop integration for improved asyncio performance on Unix.
"""

import asyncio


def use_uvloop() -> bool:
    """
    Set the current event loop policy to use uvloop, when available.

    uvloop is a fast, drop-in replacement for the default asyncio event loop,
    built on libuv. It is only supported on Unix (Linux and macOS); on Windows
    or when uvloop is not installed, this function does nothing.

    Call this once at application startup, before creating any event loop
    (e.g. before asyncio.run()).

    Returns:
        True if uvloop was successfully installed as the event loop policy,
        False otherwise (uvloop not installed or not supported on this platform).

    Example:
        >>> from genesis import use_uvloop
        >>> use_uvloop()
        True
        >>> import asyncio
        >>> asyncio.run(my_main())
    """
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        return True
    except (ImportError, OSError, AttributeError):
        return False
