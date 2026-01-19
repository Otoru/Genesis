import sys
import logging
from typing import Iterator


def get_log_level_map() -> dict[str, int]:
    """Return a mapping of log level names to values, compatible with Python < 3.11."""
    if sys.version_info >= (3, 11):
        return logging.getLevelNamesMapping()

    # Fallback for Python < 3.11
    return {
        "CRITICAL": logging.CRITICAL,
        "ERROR": logging.ERROR,
        "WARNING": logging.WARNING,
        "INFO": logging.INFO,
        "DEBUG": logging.DEBUG,
        "NOTSET": logging.NOTSET,
    }


def complete_log_levels(incomplete: str) -> Iterator[str]:
    """Autocompletion for log levels."""
    levels = [item.lower() for item in get_log_level_map().keys()]

    for item in levels:
        if item.startswith(incomplete):
            yield item
