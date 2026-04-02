import json
from unittest.mock import MagicMock, patch

import pytest

from qtrader.core.logger import QTraderLogger


@pytest.fixture
def mock_trace():
    with patch("qtrader.core.logger.TraceManager.get_current_trace") as m:
        m.return_value = "TEST-TRACE-UUID" # Simplified for test
        yield m

def test_logger_json_structure(mock_trace, capsys):
    qlogger = QTraderLogger()
    
    # 1. Log a successesful action
    qlogger.log_event(
        module="execution",
        action="order_submit",
        status="SUCCESS",
        message="Order submitted to exchange",
        latency_ms=12.5,
        metadata={"order_id": "123", "symbol": "BTC"}
    )
    
    # 2. Capture output from stdout (using loguru's behavior)
    captured = capsys.readouterr()
    log_content = captured.out.strip().split("\n")[-1] # Take the JSON line
    
    # Loguru's stdout might have some formatting, but our log_event sends a JSON string
    # We must ensure that our JSON logic is correct.
    # Note: Using serialize=True in loguru adds its own wrapper, 
    # but we are sending a json.dumps string to logger.info.
    parsed = json.loads(log_content)
    
    assert parsed["module"] == "execution"
    assert parsed["action"] == "order_submit"
    assert parsed["trace_id"] == "TEST-TRACE-UUID"
    assert parsed["latency_ms"] == 12.5
    assert parsed["metadata"]["order_id"] == "123"

def test_logger_failure_entry(mock_trace, capsys):
    qlogger = QTraderLogger()
    
    qlogger.log_event(
        module="oms",
        action="update_position",
        status="FAILURE",
        error="Position Mismatch Error",
        level="ERROR"
    )
    
    captured = capsys.readouterr()
    log_content = captured.out.strip().split("\n")[-1]
    parsed = json.loads(log_content)
    
    assert parsed["status"] == "FAILURE"
    assert parsed["error"] == "Position Mismatch Error"
    assert parsed["level"] == "ERROR"
