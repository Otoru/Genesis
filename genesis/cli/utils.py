import logging


def complete_log_levels(incomplete: str):
    """Autocompletion for log levels."""
    levels = [item.lower() for item in logging.getLevelNamesMapping().keys()]

    for item in levels:
        if item.startswith(incomplete):
            yield item
