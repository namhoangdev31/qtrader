import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.core.orchestrator import SystemState, TradingOrchestrator
from qtrader.core.types import MarketData


@pytest.fixture
def mock_orchestrator():
    orchestrator = TradingOrchestrator(
        event_bus=AsyncMock(),
        market_data_adapter=MagicMock(),
        alpha_modules=[],
        feature_validator=AsyncMock(),
        strategies=[],
        ensemble_strategy=AsyncMock(),
        portfolio_allocator=AsyncMock(),
        runtime_risk_engine=AsyncMock(),
        oms_adapter=AsyncMock(),
        state_store=AsyncMock()
    )
    return orchestrator

@pytest.mark.asyncio
async def test_fail_fast_escalation_on_handler_error(mock_orchestrator):
    """
    Verify that an unhandled exception in an orchestrator handler 
    triggers the FailFastEngine and can escalate to a system halt.
    """
    # 1. Simulate a catastrophic failure in alphabase
    from qtrader.core.system_state import state_manager
    state_manager.set_state(SystemState.RUNNING)
    
    # Add a mock alpha module that explodes
    exploding_alpha = AsyncMock()
    exploding_alpha.generate.side_effect = RuntimeError("Catastrophic Alpha Failure")
    mock_orchestrator.alpha_modules = [exploding_alpha]
    
    market_data = MarketData(
        symbol="BTC/USDT",
        timestamp=0,
        open="50000.0",
        high="51000.0",
        low="49000.0",
        close="50500.0",
        volume="1.0"
    )
    
    # 2. Mock fail_fast_engine
    with patch.object(mock_orchestrator.fail_fast_engine, 'handle_error', new_callable=AsyncMock) as mock_handle:
        await mock_orchestrator.handle_market_data(market_data)
        
        # Verify FailFastEngine was properly called
        mock_handle.assert_called_once()
        args, kwargs = mock_handle.call_args
        assert args[0] == "handle_market_data"
        assert isinstance(args[1], RuntimeError)
        assert str(args[1]) == "Catastrophic Alpha Failure"

@pytest.mark.asyncio
async def test_fail_fast_injection_into_risk_alerts(mock_orchestrator):
    """
    Verify that errors during risk alert processing trigger FailFast.
    """
    alert_data = {"trace_id": "test_trace"}
    
    # Explode Risk Alert
    mock_orchestrator.network_kill_switch.engage_hard_kill = AsyncMock(side_effect=RuntimeError("Kill Switch Failure"))
    
    with patch.object(mock_orchestrator.fail_fast_engine, 'handle_error', new_callable=AsyncMock) as mock_handle:
        await mock_orchestrator.handle_risk_alert(alert_data)
        
        mock_handle.assert_called_once()
        assert mock_handle.call_args[0][0] == "handle_risk_alert"
