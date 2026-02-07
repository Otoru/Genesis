import logging
import os
import json
import sys
from datetime import datetime, timezone
from typing import cast

from rich.logging import RichHandler

TRACE_LEVEL_NUM = 5

logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


class GenesisLogger(logging.Logger):
    def trace(self, message: str, *args, **kws) -> None:
        if self.isEnabledFor(TRACE_LEVEL_NUM):
            self._log(TRACE_LEVEL_NUM, message, args, **kws)


logging.setLoggerClass(GenesisLogger)


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
        try:
            span = trace.get_current_span()
            if span == trace.INVALID_SPAN:
                return True

            ctx = span.get_span_context()
            trace_id = trace.format_trace_id(ctx.trace_id)
            span_id = trace.format_span_id(ctx.span_id)

            record.otelTraceID = trace_id
            record.otelSpanID = span_id

            if isinstance(record.msg, str):
                record.msg = f"{record.msg} (trace_id={trace_id} span_id={span_id})"
        except Exception:
            pass

        return True


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings.
    """

    def format(self, record):
        log_record = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

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

    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    if use_json:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
    else:
        handler = RichHandler(
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            markup=True,
            show_path=False,
            show_time=True,
            omit_repeated_times=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))

    handler.addFilter(CorrelationIdFilter())

    logger.addHandler(handler)
    logger.debug(f"Logger reconfigured (json={use_json})")


def setup_logger(name: str = __name__) -> GenesisLogger:
    """Configure a logger with rich handler and conventional formatting.

    Args:
        name: The name for the logger instance

    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return cast(GenesisLogger, logger)

    handler = RichHandler(
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        markup=True,
        show_path=False,
        show_time=True,
        omit_repeated_times=False,
    )

    handler.addFilter(CorrelationIdFilter())

    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)

    log_level = get_log_level()
    logger.setLevel(log_level)
    logger.addHandler(handler)
    logger.propagate = False

    logger.debug(f"Logger initialized with level: {logging.getLevelName(log_level)}")
    return cast(GenesisLogger, logger)


logger = setup_logger(__name__)
