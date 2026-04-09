from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from qtrader.trading_system import TradingSystem, TradingSystemConfig


@pytest.fixture
def mock_ml_result():
    return {
        "decision": {
            "action": "BUY",
            "confidence": 0.8,
            "position_size_multiplier": 1.0,
            "reasoning": "Strong trend",
            "explanation": "Detailed explanation",
        }
    }


@pytest.mark.asyncio
async def test_portfolio_allocation_gate_scaling(mock_ml_result):
    # Setup config with simulation
    config = TradingSystemConfig(simulate=True)
    ts = TradingSystem(config=config)

    # Mock broker balance to simulate low capital/high concentration
    # Cash: 10,000, Max Cap: 20% (2,000), BTC: 0
    # Proposed: 1.0 BTC @ 50,000 (50,000 USD) -> Should be scaled down significantly
    ts.broker.get_balance = MagicMock(return_value={"USD": 10000.0})
    ts.broker.get_paper_balance = MagicMock(
        return_value={
            "equity": 10000.0,
            "cash": 10000.0,
            "realized_pnl": 0.0,
            "total_commissions": 0.0,
        }
    )

    # We mock _run_ml_alpha and _get_market_data to avoid side effects
    ts._get_market_data = MagicMock(return_value={"price": 50000.0})
    ts._run_ml_alpha = MagicMock(return_value=mock_ml_result)

    # Mock execute_order to capture the signal
    ts._execute_order = MagicMock()
    ts._process_fills = MagicMock()

    # Run the pipeline for BTC-USD
    await ts._process_symbol("BTC-USD")

    # Verify that the signal was scaled down
    # Expected Approved Notional: 10,000 * 0.2 = 2,000
    # Expected Qty: 2,000 / 50,000 = 0.04
    ts._execute_order.assert_called_once()
    signal = ts._execute_order.call_args[0][0]
    assert signal["position_size_multiplier"] <= 0.041  # Allow some precision delta
    assert signal["position_size_multiplier"] > 0


@pytest.mark.asyncio
async def test_shadow_gate_blocks_live(mock_ml_result):
    config = TradingSystemConfig(simulate=True, shadow_min_days=7)
    ts = TradingSystem(config=config)

    # Mock shadow engine to report duration NOT met
    ts.shadow_engine.is_shadow_duration_met = MagicMock(return_value=False)

    ts.broker.get_balance = MagicMock(return_value={"USD": 100000.0})
    ts._get_market_data = MagicMock(return_value={"price": 50000.0})
    ts._run_ml_alpha = MagicMock(return_value=mock_ml_result)

    # Mock execute_order
    ts._execute_order = MagicMock()

    await ts._process_symbol("BTC-USD")

    # Verify that order execution was BLOCKED
    ts._execute_order.assert_not_called()
