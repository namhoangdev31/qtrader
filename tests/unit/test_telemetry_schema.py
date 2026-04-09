import pytest

from qtrader.trading_system import TradingSystem, TradingSystemConfig


def test_trading_system_status_schema():
    """Verify that TradingSystem.get_status contains the 'running' key."""
    config = TradingSystemConfig(simulate=True)
    ts = TradingSystem(config=config)

    status = ts.get_status()
    assert "status" in status
    assert "running" in status
    assert isinstance(status["running"], bool)
    assert status["status"] == "IDLE"
    assert status["running"] is False


def test_trading_system_module_traces_schema():
    """Verify that TradingSystem._get_module_traces contains the keys for the FlowVisualizer."""
    config = TradingSystemConfig(simulate=True)
    ts = TradingSystem(config=config)

    # Mock some ML result
    ml_result = {"confidence": 0.8, "indicators": {"rsi": 65.0}}

    traces = ts._get_module_traces("BTC-USD", ml_result)

    # Check for legacy and new keys
    assert "AlphaEngine" in traces
    assert "alpha" in traces
    assert "ingestion" in traces
    assert "risk" in traces
    assert "execution" in traces

    # Check specific fields expected by FlowVisualizer
    assert "price" in traces["ingestion"]
    assert "rsi" in traces["alpha"]["indicators"]
    assert "initial_stop_loss" in traces["risk"]
    assert "slippage_bps" in traces["execution"]


def test_paper_engine_initial_traces():
    """Verify that PaperTradingEngine initializes with all necessary trace keys."""
    from qtrader.execution.paper_engine import PaperTradingEngine

    engine = PaperTradingEngine(starting_capital=1000.0)

    traces = engine._last_trace["module_traces"]
    assert "ingestion" in traces
    assert "alpha" in traces
    assert "risk" in traces
    assert "execution" in traces
    assert traces["execution"]["status"] == "AWAITING"
