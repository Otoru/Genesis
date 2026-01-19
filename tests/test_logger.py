import json
import logging
from unittest import mock
from genesis.logger import reconfigure_logger, JSONFormatter, CorrelationIdFilter

def test_json_formatter():
    formatter = JSONFormatter()
    record = logging.LogRecord("test", logging.INFO, "path", 10, "message", (), None)
    
    record.otelTraceID = "12345"
    record.otelSpanID = "67890"

    output = formatter.format(record)
    data = json.loads(output)
    
    assert data["level"] == "INFO"
    assert data["message"] == "message"
    assert data["trace_id"] == "12345"
    assert data["span_id"] == "67890"

def test_reconfigure_logger_json():
    with mock.patch("logging.Logger.addHandler") as mock_add_handler:
        with mock.patch("genesis.logger.RichHandler") as mock_rich:
            reconfigure_logger(use_json=True)
            mock_rich.assert_not_called()
            assert mock_add_handler.called

def test_correlation_id_filter():
    filter_ = CorrelationIdFilter()
    record = logging.LogRecord("test", logging.INFO, "path", 10, "message", (), None)
    
    with mock.patch("opentelemetry.trace.get_current_span") as mock_get_span:
        mock_get_span.return_value = mock.Mock()
        from opentelemetry import trace
        mock_get_span.return_value = trace.INVALID_SPAN
        
        assert filter_.filter(record) is True
        
        mock_span = mock.Mock()
        mock_context = mock.Mock()
        mock_context.trace_id = 0x12345678123456781234567812345678
        mock_context.span_id = 0x1234567812345678
        mock_span.get_span_context.return_value = mock_context
        mock_get_span.return_value = mock_span
        
        record.msg = "message"
        assert filter_.filter(record) is True
        assert hasattr(record, "otelTraceID")
        assert "trace_id=" in record.msg
