import pytest
from qtrader.core.decimal_adapter import math_authority
from qtrader.core.types import MarketData
from qtrader.core.orchestrator import TradingOrchestrator
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_orchestrator():
    return TradingOrchestrator(
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

@pytest.mark.asyncio
async def test_numeric_integrity_violation(mock_orchestrator):
    """
    Verify that passing float primitives to the orchestrator triggers 
    a Numerical Integrity Violation.
    """
    # Create market data with float values
    # In strict mode, math_authority.d(float) raises TypeError
    market_data = MarketData(
        symbol="BTC/USDT",
        timestamp=0,
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,  # FLOAT
        volume=1.0      # FLOAT
    )
    
    # Setting orchestrator to RUNNING to allow execution
    from qtrader.core.system_state import state_manager, SystemState
    state_manager.set_state(SystemState.RUNNING)
    
    # We expect FailFastEngine to intercept the TypeError
    with patch.object(mock_orchestrator.fail_fast_engine, 'handle_error', new_callable=AsyncMock) as mock_fail_fast:
        await mock_orchestrator.handle_market_data(market_data)
        
        # Verify FailFast was called with TypeError from DecimalAdapter
        mock_fail_fast.assert_called_once()
        args, kwargs = mock_fail_fast.call_args
        assert args[0] == "handle_market_data"
        assert isinstance(args[1], TypeError)
        assert "Numerical Integrity Violation" in str(args[1])

from unittest.mock import patch
