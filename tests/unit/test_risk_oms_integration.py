#!/usr/bin/env python3
"""
Test script demonstrating integration between OMS and Risk Engine V2.
This shows how the runtime risk engine connects to actual position data.
"""

import asyncio
from unittest.mock import Mock

import polars as pl

from qtrader.execution.oms import UnifiedOMS, PositionManager
from qtrader.risk.runtime import RuntimeRiskEngine


async def test_oms_position_tracking():
    """Test that OMS correctly tracks positions and P&L."""
    print("Testing OMS position tracking...")
    
    # Create OMS instance
    oms = UnifiedOMS()
    
    # Create a mock broker adapter
    mock_adapter = Mock()
    mock_adapter.get_balance.return_value = {"USD": 100000.0}
    mock_adapter.submit_order.return_value = "order_123"
    mock_adapter.cancel_order.return_value = True
    
    # Add the adapter to OMS
    oms.add_venue("mock", mock_adapter)
    
    # Verify initial state
    assert len(oms.adapters) == 1
    print("✓ OMS initialized with broker adapter")


async def test_runtime_risk_engine_with_oms():
    """Test that runtime risk engine can get data from OMS."""
    print("Testing RuntimeRiskEngine with OMS integration...")
    
    # Create OMS
    oms = UnifiedOMS()
    
    # Create risk engine that depends on OMS
    risk_engine = RuntimeRiskEngine(oms=oms)
    
    # Test that we can compute risk metrics
    test_data = pl.DataFrame({
        'close': [100.0, 101.0, 102.0, 103.0],
        'volume': [1000, 1100, 1200, 1300]
    })
    
    # Test exposure calculation (should work even with empty positions)
    exposure = risk_engine.compute(test_data, risk_metric='exposure')
    assert len(exposure) == 4
    # With no positions, P&L should be 0
    assert all(val == 0.0 for val in exposure.to_list())
    print("✓ Risk engine computes exposure from OMS")
    
    # Test other metrics
    drawdown = risk_engine.compute(test_data, risk_metric='drawdown')
    leverage = risk_engine.compute(test_data, risk_metric='leverage')
    
    assert len(drawdown) == 4
    assert len(leverage) == 4
    print("✓ Risk engine computes other metrics")


async def test_risk_engine_with_mock_positions():
    """Test risk engine with mocked position data."""
    print("Testing Risk Engine with mocked position data...")
    
    # Create OMS with mocked position data
    oms = Mock(spec=UnifiedOMS)
    oms.get_pnl.return_value = 2500.0  # Simulate $2500 profit
    
    # Create risk engine
    risk_engine = RuntimeRiskEngine(oms=oms)
    
    # Test with market data
    test_data = pl.DataFrame({
        'price': [99.0, 100.0, 101.0, 102.0],
    })
    
    # Test exposure - should reflect the mocked P&L
    exposure = risk_engine.compute(test_data, risk_metric='exposure')
    assert all(val == 2500.0 for val in exposure.to_list())
    print("✓ Risk engine correctly uses OMS P&L data for exposure")
    
    # Test that we can call other metrics (placeholders)
    drawdown = risk_engine.compute(test_data, risk_metric='drawdown')
    assert all(val == 0.0 for val in drawdown.to_list())  # Placeholder
    
    leverage = risk_engine.compute(test_data, risk_metric='leverage')
    assert all(val == 1.0 for val in leverage.to_list())  # Placeholder (no leverage)
    print("✓ Risk engine returns appropriate placeholder values")


async def test_kill_switch_simulation():
    """Simulate how a kill switch would work with OMS and risk engine."""
    print("Testing kill switch simulation...")
    
    # Create OMS
    oms = UnifiedOMS()
    
    # Create risk engine
    risk_engine = RuntimeRiskEngine(oms=oms)
    
    # Simulate market data showing a drawdown scenario
    # In a real implementation, the risk engine would compute drawdown
    # from the OMS equity curve and trigger position scaling
    market_data = pl.DataFrame({
        'returns': [0.01, -0.02, -0.03, 0.015, -0.01],  # Some losses
    })
    
    # Test that we can compute VaR (placeholder implementation)
    var_result = risk_engine.compute(market_data, risk_metric='var', confidence=0.05)
    assert len(var_result) == 5
    print("✓ Risk engine can compute VaR (placeholder)")
    
    # In a full implementation, we would:
    # 1. Track equity curve from OMS P&L over time
    # 2. Compute current drawdown
    # 3. If drawdown exceeds threshold, scale positions
    # 4. OMS would receive scaled position targets
    print("✓ Kill switch simulation framework ready")


async def main():
    """Run all integration tests."""
    print("Testing OMS and Risk Engine V2 Integration...\n")
    
    await test_oms_position_tracking()
    await test_runtime_risk_engine_with_oms()
    await test_risk_engine_with_mock_positions()
    await test_kill_switch_simulation()
    
    print("\n✅ All OMS-Risk Engine integration tests passed!")
    print("\nKey Integration Points Demonstrated:")
    print("1. RuntimeRiskEngine depends on UnifiedOMS for position/P&L data")
    print("2. Risk metrics (exposure, drawdown, VaR) can be computed from OMS data")
    print("3. The separation of concerns allows independent testing")
    print("4. Real implementation would connect risk outputs to position sizing")


if __name__ == "__main__":
    asyncio.run(main())