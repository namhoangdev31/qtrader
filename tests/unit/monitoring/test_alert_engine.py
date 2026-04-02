import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from loguru import logger

from qtrader.monitoring.alert_engine import AlertEngine
from qtrader.monitoring.metrics_collector import MetricsCollector


@pytest.fixture
def alert_engine():
    # Fresh engine with critical rules
    policy = {
        "rules": {
            "critical_latency_p99": {
                "metric": "execution_latency_ms",
                "stat": "p99",
                "threshold": 80.0,
                "severity": "CRITICAL",
                "action": "HALT"
            },
            "high_error_rate": {
                "metric": "error_rate",
                "stat": "value",
                "threshold": 5.0,
                "severity": "CRITICAL",
                "action": "ALERT"
            }
        },
        "channels": {
            "telegram": {"enabled": True},
            "email": {"enabled": True}
        }
    }
    engine = AlertEngine(policy)
    # Manually inject mock collector
    engine._metrics_collector = MagicMock()
    return engine

def test_alert_engine_breach_detection(alert_engine):
    # Setup Mock Data
    alert_engine._metrics_collector.flush_report.return_value = {
        "counters": {"error_rate": 8.0},
        "gauges": {},
        "summaries": {
            "execution_latency_ms": {"p99": 85.0}
        }
    }
    
    # Perform the check
    triggered = alert_engine.check_alerts()
    
    # Assert 100% breach detection
    assert "critical_latency_p99" in triggered
    assert "high_error_rate" in triggered
    assert len(triggered) == 2

def test_alert_engine_multi_channel_dispatch(alert_engine):
    # Setup Mock Data
    alert_engine._metrics_collector.flush_report.return_value = {
        "counters": {"error_rate": 8.0},
        "gauges": {},
        "summaries": {"execution_latency_ms": {"p99": 85.0}}
    }
    
    # Capture loguru output
    output = StringIO()
    hid = logger.add(output, format="{message}")
    
    try:
        alert_engine.check_alerts()
        log_content = output.getvalue()
        
        # Assert logs for Telegram/Email Mocks
        assert "[TELEGRAM] PUSH ->" in log_content
        assert "[EMAIL] SEND ->" in log_content
        assert "ALERT [CRITICAL] Breach='critical_latency_p99'" in log_content
    finally:
        logger.remove(hid)

def test_alert_engine_cooldown_governance(alert_engine):
    # Setup Mock Data
    alert_engine._metrics_collector.flush_report.return_value = {
        "counters": {"error_rate": 8.0},
        "gauges": {},
        "summaries": {"execution_latency_ms": {"p99": 85.0}}
    }
    
    output = StringIO()
    hid = logger.add(output, format="{message}")
    
    try:
        # Trigger first alert
        alert_engine.check_alerts()
        count_init = output.getvalue().count("critical_latency_p99")
        
        # Trigger second alert immediately - should be COOLING DOWN
        alert_engine.check_alerts()
        count_after = output.getvalue().count("critical_latency_p99")
        
        # Number of alerts should NOT increase (cooldown active)
        assert count_after == count_init
    finally:
        logger.remove(hid)
