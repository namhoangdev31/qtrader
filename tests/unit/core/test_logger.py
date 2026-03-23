import json
import logging
import io
import sys
from qtrader.core.logger import StructuredLogger

def test_structured_logger_json_output():
    # Redirect stdout to capture logs
    log_capture = io.StringIO()
    
    # Create logger with custom StreamHandler
    logger_instance = StructuredLogger(name="test_logger", level=logging.INFO)
    logger_instance.logger.handlers.clear()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(StructuredLogger.JSONFormatter())
    logger_instance.logger.addHandler(handler)
    
    # Log a message
    test_msg = "Test message"
    logger_instance.info(test_msg, extra_field="extra_value")
    
    # Capture output
    output = log_capture.getvalue().strip()
    log_data = json.loads(output)
    
    assert log_data["message"] == test_msg
    assert log_data["level"] == "INFO"
    assert log_data["logger"] == "test_logger"
    assert log_data["extra_field"] == "extra_value"
    assert "timestamp" in log_data
    assert "correlation_id" in log_data

def test_structured_logger_levels():
    log_capture = io.StringIO()
    logger_instance = StructuredLogger(name="test_levels", level=logging.DEBUG)
    logger_instance.logger.handlers.clear()
    handler = logging.StreamHandler(log_capture)
    handler.setFormatter(StructuredLogger.JSONFormatter())
    logger_instance.logger.addHandler(handler)
    
    logger_instance.debug("debug message")
    logger_instance.error("error message")
    
    output = log_capture.getvalue().strip().split('\n')
    assert len(output) == 2
    assert json.loads(output[0])["level"] == "DEBUG"
    assert json.loads(output[1])["level"] == "ERROR"
