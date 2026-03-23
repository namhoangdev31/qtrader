import pytest
from unittest.mock import MagicMock
from qtrader.feedback.live_feedback_engine import LiveFeedbackEngine

def test_live_feedback_engine_init():
    engine = LiveFeedbackEngine(metrics_db="test_db")
    assert engine.metrics_db == "test_db"
    assert len(engine.subscribers) == 0

def test_live_feedback_engine_subscribe():
    engine = LiveFeedbackEngine()
    mock_subscriber = MagicMock()
    engine.subscribe(mock_subscriber)
    assert mock_subscriber in engine.subscribers

def test_live_feedback_engine_publish():
    engine = LiveFeedbackEngine()
    mock_subscriber = MagicMock()
    engine.subscribe(mock_subscriber)
    
    engine.publish_metric("latency", 50.0)
    mock_subscriber.on_metric.assert_called_once_with("latency", 50.0)
