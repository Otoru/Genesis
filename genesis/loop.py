"""
Event loop utilities.

Provides optional uvloop integration for improved asyncio performance on Unix.
"""

import asyncio
import warnings


def new_event_loop() -> asyncio.AbstractEventLoop:
    """
    Create a new event loop, backed by uvloop when available.

    uvloop is a fast, drop-in replacement for the default asyncio event loop,
    built on libuv. It is only supported on Unix (Linux and macOS); on Windows
    or when uvloop is not installed, this returns a default asyncio loop.

    Pass it as the ``loop_factory`` of ``asyncio.Runner`` (or of ``asyncio.run``
    on Python 3.12+). Unlike an event loop policy, it changes no global state.

    Example:
        >>> import asyncio
        >>> from genesis import new_event_loop
        >>> with asyncio.Runner(loop_factory=new_event_loop) as runner:
        ...     runner.run(my_main())
    """
    try:
        import uvloop
    except (ImportError, OSError, AttributeError):
        return asyncio.new_event_loop()
    return uvloop.new_event_loop()


def use_uvloop() -> bool:
    """
    Set the current event loop policy to use uvloop, when available.

    Deprecated: asyncio event loop policies are deprecated since Python 3.14
    and removed in 3.16. Pass ``new_event_loop`` as the ``loop_factory`` of
    ``asyncio.Runner`` instead.

    Call this once at application startup, before creating any event loop
    (e.g. before asyncio.run()).

    Returns:
        True if uvloop was successfully installed as the event loop policy,
        False otherwise (uvloop not installed, not supported on this platform,
        or event loop policies no longer exist).
    """
    warnings.warn(
        "use_uvloop() is deprecated; pass genesis.new_event_loop as the "
        "loop_factory of asyncio.Runner instead",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        return True
    except (ImportError, OSError, AttributeError):
        return False
