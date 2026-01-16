import logging
import os
import json
import sys
from datetime import datetime, timezone
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


from opentelemetry import trace


class CorrelationIdFilter(logging.Filter):
    """
    Log filter to inject the current OpenTelemetry trace and span IDs into the log record.
    """

    def filter(self, record):
        span = trace.get_current_span()
        if span == trace.INVALID_SPAN:
            # Optionally don't clutter logs if no trace
            return True
        
        ctx = span.get_span_context()
        trace_id = trace.format_trace_id(ctx.trace_id)
        span_id = trace.format_span_id(ctx.span_id)
        
        # Set attributes for JSONFormatter
        record.otelTraceID = trace_id
        record.otelSpanID = span_id
        
        # Append to the message for Text/Rich logging
        # We need to handle if msg is not a string (rare but possible)
        if isinstance(record.msg, str):
            # Use parentheses to avoid Rich markup collision
            record.msg = f"{record.msg} (trace_id={trace_id} span_id={span_id})"
            
        return True


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings.
    """

    def format(self, record):
        # Create a dictionary with log record attributes
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        # Add extra fields (trace_id, span_id) if available (set by CorrelationIdFilter)
        # Note: CorrelationIdFilter might have set them on the record options
        if hasattr(record, "otelTraceID") and record.otelTraceID != "0":
            log_record["trace_id"] = record.otelTraceID
        if hasattr(record, "otelSpanID") and record.otelSpanID != "0":
            log_record["span_id"] = record.otelSpanID
            
        return json.dumps(log_record)


def reconfigure_logger(use_json: bool = False) -> None:
    """
    Reconfigure the logger to use JSON format or Rich format.
    
    Args:
        use_json: If True, use JSONFormatter. If False, use RichHandler.
    """
    logger = logging.getLogger(__name__)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        
    if use_json:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
    else:
        # Re-add RichHandler (same config as setup_logger)
        handler = RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            show_path=False,
            show_time=True,
            omit_repeated_times=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    
    # Always add the filter
    handler.addFilter(CorrelationIdFilter())
    
    logger.addHandler(handler)
    logger.debug(f"Logger reconfigured (json={use_json})")


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
    
    # Add OpenTelemetry correlation filter
    handler.addFilter(CorrelationIdFilter())

    # Update formatter to include trace/span IDs
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    # Get log level from environment variable
    log_level = get_log_level()
    logger.setLevel(log_level)
    logger.addHandler(handler)
    logger.propagate = False

    logger.debug(f"Logger initialized with level: {logging.getLevelName(log_level)}")
    return logger


# Create default logger
logger = setup_logger(__name__)
