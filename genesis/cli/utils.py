import logging
from typing import Iterator


def get_log_level_map() -> dict[str, int]:
    """Return a mapping of log level names to values."""
    return logging.getLevelNamesMapping()


def complete_log_levels(incomplete: str) -> Iterator[str]:
    """Autocompletion for log levels."""
    levels = [item.lower() for item in get_log_level_map().keys()]

    for item in levels:
        if item.startswith(incomplete):
            yield item
