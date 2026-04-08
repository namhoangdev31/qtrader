import pytest
import polars as pl
from qtrader.risk.realtime import RealTimeRiskEngine
from qtrader.core.events import RiskEvent

def test_rust_risk_integration_drawdown():
    """Verify that RealTimeRiskEngine catches drawdown breaches via Rust Core."""
    engine = RealTimeRiskEngine(limits=[])
    
    # Set 15% drawdown limit in Rust (initialized in __post_init__)
    # We simulate a 20% drawdown
    engine.hwm = 100000.0
    engine.equity = 80000.0
    
    # We need at least one position row for the check_all_limits to proceed with gross_exposure
    engine.positions = pl.DataFrame({
        "symbol": ["BTC"],
        "qty": [2.0],
        "price": [40000.0],
        "market_value": [80000.0],
        "weight": [1.0]
    })
    
    breaches = engine.check_all_limits()
    assert len(breaches) > 0
    assert any("CRITICAL_DRAWDOWN" in b.reason for b in breaches)
    assert any(b.metadata.get("source") == "RUST_CORE" for b in breaches)

def test_rust_risk_integration_leverage():
    """Verify that RealTimeRiskEngine catches leverage breaches via Rust Core."""
    engine = RealTimeRiskEngine(limits=[])
    
    # 2x Leverage limit
    engine.hwm = 100000.0
    engine.equity = 100000.0
    
    # Simulate 3x leverage (300k exposure on 100k equity)
    engine.positions = pl.DataFrame({
        "symbol": ["BTC"],
        "qty": [10.0],
        "price": [30000.0],
        "market_value": [300000.0],
        "weight": [1.0]
    })
    
    breaches = engine.check_all_limits()
    assert len(breaches) > 0
    assert any("LEVERAGE_EXCEEDED" in b.reason for b in breaches)

@pytest.mark.asyncio
async def test_publish_breaches_triggers_kill_switch():
    """Verify that a Rust-detected breach triggers the global kill switch."""
    from unittest.mock import MagicMock, AsyncMock
    
    kill_switch = MagicMock()
    kill_switch.trigger_on_critical_failure = MagicMock()
    
    engine = RealTimeRiskEngine(limits=[], kill_switch=kill_switch)
    engine.hwm = 100000.0
    engine.equity = 80000.0 # 20% DD
    engine.positions = pl.DataFrame({
        "symbol": ["BTC"],
        "qty": [2.0],
        "price": [40000.0],
        "market_value": [80000.0],
        "weight": [1.0]
    })
    
    await engine.publish_breaches()
    
    kill_switch.trigger_on_critical_failure.assert_called_once()
    args, _ = kill_switch.trigger_on_critical_failure.call_args
    assert args[0] == "RISK_LIMIT_BREACH"
    assert "Critical risk breach detected in RUST_CORE" in args[1]
