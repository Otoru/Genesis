import logging
import os
from rich.logging import RichHandler

TRACE_LEVEL_NUM = 5

logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)


logging.Logger.trace = trace


def get_log_level() -> int:
    """
    Get log level from environment variable or return default (INFO).

    Valid values for LOG_LEVEL are:
     - TRACE
     - DEBUG
     - INFO
     - WARNING
     - ERROR
     - CRITICAL

    Returns logging level constant.
    """
    level_map = {
        "TRACE": TRACE_LEVEL_NUM,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    env_level = os.getenv("GENESIS_LOG_LEVEL", "INFO").upper()
    return level_map.get(env_level, logging.INFO)


def setup_logger(name: str = __name__) -> logging.Logger:
    """Configure a logger with rich handler and conventional formatting.

    Args:
        name: The name for the logger instance

    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    handler = RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
        show_path=False,
        show_time=True,
        omit_repeated_times=False,
    )

    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    # Get log level from environment variable
    log_level = get_log_level()
    logger.setLevel(log_level)
    logger.addHandler(handler)
    
    # Check if log file path is specified in environment
    log_file_path = os.getenv("GENESIS_LOG_FILE")
    if log_file_path:
        # Create file handler with clean formatting and line buffering
        file_handler = logging.FileHandler(log_file_path, mode='a', encoding='utf-8', delay=False)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(log_level)
        
        # Set the handler to flush after each log entry
        file_handler.flush = lambda: file_handler.stream.flush()
        
        logger.addHandler(file_handler)
        logger.debug(f"Added file logging to: {log_file_path}")
    logger.propagate = False

    logger.debug(f"Logger initialized with level: {logging.getLevelName(log_level)}")
    return logger


# Create default logger
logger = setup_logger(__name__)
