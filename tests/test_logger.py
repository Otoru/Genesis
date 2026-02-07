"""Tests for genesis.logger module."""

import logging
import json
import os
from unittest.mock import Mock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis.observability.logger import (
    get_log_level,
    setup_logger,
    reconfigure_logger,
    CorrelationIdFilter,
    JSONFormatter,
    TRACE_LEVEL_NUM,
)


log_level_cases = [
    {"env_value": None, "expected": logging.INFO, "description": "default"},
    {"env_value": "TRACE", "expected": TRACE_LEVEL_NUM, "description": "trace"},
    {"env_value": "DEBUG", "expected": logging.DEBUG, "description": "debug"},
    {"env_value": "INFO", "expected": logging.INFO, "description": "info"},
    {"env_value": "WARNING", "expected": logging.WARNING, "description": "warning"},
    {"env_value": "ERROR", "expected": logging.ERROR, "description": "error"},
    {"env_value": "CRITICAL", "expected": logging.CRITICAL, "description": "critical"},
    {
        "env_value": "INVALID",
        "expected": logging.INFO,
        "description": "invalid_defaults_to_info",
    },
]


@pytest.mark.parametrize("case", log_level_cases)
def test_get_log_level(case):
    env_value = case["env_value"]
    expected = case["expected"]

    if env_value is None:
        with patch.dict(os.environ, {}, clear=True):
            level = get_log_level()
            assert level == expected
    else:
        with patch.dict(os.environ, {"GENESIS_LOG_LEVEL": env_value}):
            level = get_log_level()
            assert level == expected


def test_trace_method():
    logger = logging.getLogger("test_trace")
    logger.setLevel(TRACE_LEVEL_NUM)

    handler = logging.StreamHandler()
    handler.setLevel(TRACE_LEVEL_NUM)
    logger.addHandler(handler)

    logger.trace("Test trace message")  # type: ignore

    logger.removeHandler(handler)


def test_correlation_id_filter_no_span():
    filter_obj = CorrelationIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    result = filter_obj.filter(record)
    assert result is True
    assert not hasattr(record, "otelTraceID")


def test_correlation_id_filter_with_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    tracer = trace.get_tracer(__name__)

    filter_obj = CorrelationIdFilter()

    with tracer.start_as_current_span("test_span"):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = filter_obj.filter(record)
        assert result is True
        assert hasattr(record, "otelTraceID")
        assert hasattr(record, "otelSpanID")
        assert "trace_id=" in record.msg
        assert "span_id=" in record.msg


def test_json_formatter_basic():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["message"] == "Test message"
    assert data["logger"] == "test.logger"
    assert "timestamp" in data


def test_json_formatter_with_exception():
    formatter = JSONFormatter()

    try:
        raise ValueError("Test error")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["level"] == "ERROR"
        assert data["message"] == "Error occurred"
        assert "exception" in data
        assert "ValueError: Test error" in data["exception"]


def test_json_formatter_with_trace_ids():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    record.otelTraceID = "abc123"
    record.otelSpanID = "def456"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["trace_id"] == "abc123"
    assert data["span_id"] == "def456"


def test_json_formatter_skips_zero_trace_ids():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    record.otelTraceID = "0"
    record.otelSpanID = "0"

    output = formatter.format(record)
    data = json.loads(output)

    assert "trace_id" not in data
    assert "span_id" not in data


def test_reconfigure_logger_json():
    reconfigure_logger(use_json=True)

    logger = logging.getLogger("genesis.observability.logger")
    assert len(logger.handlers) > 0

    handler = logger.handlers[0]
    assert isinstance(handler.formatter, JSONFormatter)


def test_reconfigure_logger_rich():
    reconfigure_logger(use_json=False)

    logger = logging.getLogger("genesis.observability.logger")
    assert len(logger.handlers) > 0


def test_setup_logger_creates_logger():
    logger_name = "test_setup_new"
    logger = setup_logger(logger_name)

    assert logger is not None
    assert logger.name == logger_name
    assert len(logger.handlers) > 0
    assert logger.propagate is False


def test_setup_logger_returns_existing():
    logger_name = "test_setup_existing"

    logger1 = setup_logger(logger_name)
    handler_count = len(logger1.handlers)

    logger2 = setup_logger(logger_name)

    assert logger1 is logger2
    assert len(logger2.handlers) == handler_count
