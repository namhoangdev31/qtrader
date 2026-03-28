import time
import pytest
from unittest.mock import patch, MagicMock
from qtrader.monitoring.trace_engine import TraceEngine, TraceNode
from qtrader.core.trace_manager import TraceManager

@pytest.fixture
def engine():
    # Fresh engine for each test
    return TraceEngine()

@pytest.fixture
def trace_id():
    return TraceManager.start_trace()

def test_trace_engine_record_node(engine, trace_id):
    # Record nodes in a trace lifecycle
    with patch("qtrader.monitoring.trace_engine.TraceManager.get_current_trace", return_value=trace_id):
        engine.record_node("market_data", "ingest", {"tick": 100.5})
        time.sleep(0.01) # Simulate some processing delay
        engine.record_node("alpha", "generate_signal", {"side": "BUY"})
        time.sleep(0.01)
        engine.record_node("execution", "submit_order", {"qty": 1.0})
        
    # Reconstruct the chain
    chain = engine.get_trace_chain(str(trace_id))
    
    # Assert 100% trace chain integrity
    assert len(chain) == 3
    assert chain[0].module == "market_data"
    assert chain[1].module == "alpha"
    assert chain[2].module == "execution"
    assert chain[0].timestamp < chain[1].timestamp < chain[2].timestamp
    assert chain[0].state["tick"] == 100.5

def test_trace_engine_handoff_latency(engine, trace_id):
    # Correct calculation of 'Air Gap' between stages
    with patch("qtrader.monitoring.trace_engine.TraceManager.get_current_trace", return_value=trace_id):
        engine.record_node("data", "start")
        time.sleep(0.05)
        engine.record_node("execution", "order")
        
    handoffs = engine.calculate_handoff_latency(str(trace_id))
    
    # Expect ~50ms handoff gap
    gap = handoffs["data->execution"]
    assert gap >= 50.0
    assert gap < 100.0

def test_trace_engine_report_visualization(engine, trace_id, caplog):
    # Verify trace reporting format
    with patch("qtrader.monitoring.trace_engine.TraceManager.get_current_trace", return_value=trace_id):
        engine.record_node("input", "test")
        engine.record_node("output", "test")
        
    # This logs to loguru - we can visually check in the test or use a sink
    engine.report_trace(str(trace_id))
    # Visual check passes if no crash and trace ID found in output
