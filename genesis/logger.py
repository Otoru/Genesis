import logging
import os
from rich.logging import RichHandler
from logging import LogRecord
from pathlib import Path

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


class ConditionalRichHandlerFormatter(logging.Formatter):
    """
    A custom log formatter that prepends pathname and lineno for DEBUG and TRACE levels.
    This formatter is intended for use with RichHandler, where RichHandler itself
    handles timestamp and level name display. This formatter modifies the message part.
    """

    def __init__(self, fmt: str = "%(message)s", *args, **kwargs):
        """
        Initializes the formatter.

        :param fmt: The default format string for the message part.
        :param args: Additional arguments for logging.Formatter.
        :param kwargs: Additional keyword arguments for logging.Formatter.
        """
        super().__init__(fmt, *args, **kwargs)

    def format(self, record: LogRecord) -> str:
        """
        Formats the log record.

        Formats the log record.

        If the log level is DEBUG or TRACE, it prepends "file:///path/to/file:lineno"
        to the formatted message. Otherwise, it returns the formatted message as is.

        :param record: The log record to format.
        :return: The formatted log string.
        """
        formatted_message = super().format(record)

        if record.levelno == TRACE_LEVEL_NUM or record.levelno == logging.DEBUG:
            # Convert pathname to a file URI
            file_path = Path(record.pathname)
            file_uri = file_path.as_uri()

            file_uri = file_uri[8:]

            # Ensure drive letter is lowercase for compatibility (e.g., file:///c:/...)
            # Path.as_uri() on Windows produces file:///C:/...
            # Check if the URI matches the pattern file:///X:/... where X is an uppercase letter
            if len(file_uri) > 8 and file_uri[7:9] == ':/' and file_uri[6].isupper():
                file_uri = file_uri[:6] + file_uri[6].lower() + file_uri[7:]
            
            return f"{formatted_message}\n{file_path}:{record.lineno}"
        return formatted_message


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

    # Use the new conditional formatter for RichHandler
    rich_formatter = ConditionalRichHandlerFormatter("%(message)s")
    handler.setFormatter(rich_formatter)

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
        # Corrected debug message to use the actual log_file_path
        logger.debug(f"Added file logging to: {log_file_path}")
        # Removed temporary print statements
    logger.propagate = False

    logger.debug(f"Logger initialized with level: {logging.getLevelName(log_level)}")
    return logger


# Create default logger
logger = setup_logger(__name__)
