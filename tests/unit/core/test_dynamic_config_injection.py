from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.core.events import EventType
from qtrader.core.orchestrator import SystemState, TradingOrchestrator
from qtrader.core.types import SignalEvent


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
async def test_dynamic_config_in_risk_handler(mock_orchestrator):
    """
    Verify that updating the max_var in ConfigManager is immediately 
    honored by the handle_signals (Risk Stage).
    """
    # 1. Start in RUNNING state
    from qtrader.core.system_state import state_manager
    state_manager.set_state(SystemState.RUNNING)
    
    # 2. Mock high signal strength (likely to trigger high allocation)
    signal_data = {
        "signal": {"signal_type": "BUY", "strength": "0.9"},
        "symbol": "BTC/USDT",
        "timestamp": "2026-03-31T12:00:00Z"
    }
    
    # 3. First, set a very loose max_var (should pass)
    await mock_orchestrator.config_manager.update("max_var", 0.9)
    
    # Mock allocator to return large weight
    mock_orchestrator.portfolio_allocator.allocate = AsyncMock(
        return_value=MagicMock(weights={"BTC/USDT": Decimal("1.0")})
    )
    # Mock risk metrics to show 10% VaR
    mock_orchestrator.runtime_risk_engine.evaluate_risk = AsyncMock(
        return_value=MagicMock(portfolio_var=Decimal("0.1"), max_drawdown=Decimal("0.0"), leverage=Decimal("1.0"))
    )
    
    # Initial run (Should pass)
    with patch.object(mock_orchestrator.event_bus, 'publish', new_callable=AsyncMock) as mock_publish:
        await mock_orchestrator.handle_signals(signal_data)
        # Check that it published to EventType.ORDERS
        mock_publish.assert_any_call(EventType.ORDERS, pytest.any(dict))
    
    # 4. Now update max_var to be very tight (0.01)
    await mock_orchestrator.config_manager.update("max_var", 0.01)
    
    # Second run (Should fail RISK)
    with patch.object(mock_orchestrator.event_bus, 'publish', new_callable=AsyncMock) as mock_publish:
        await mock_orchestrator.handle_signals(signal_data)
        # Check that it published to EventType.RISK_ALERT instead of EventType.ORDERS
        mock_publish.assert_any_call(EventType.RISK_ALERT, pytest.any(dict))
        # Ensure it NEVER published an order this time
        for call in mock_publish.call_args_list:
            assert call[0][0] != EventType.ORDERS
