#!/usr/bin/env python3
"""
Test script for RuntimeRiskEngine implementation.
"""

import asyncio
from unittest.mock import Mock

import polars as pl

from qtrader.execution.oms import UnifiedOMS
from qtrader.risk.runtime import RuntimeRiskEngine, create_runtime_risk_engine


async def test_runtime_risk_engine_creation():
    """Test that we can create a RuntimeRiskEngine."""
    print("Testing RuntimeRiskEngine creation...")
    
    # Create a mock OMS
    mock_oms = Mock(spec=UnifiedOMS)
    mock_oms.get_pnl.return_value = 1000.0
    
    # Create the risk engine
    risk_engine = RuntimeRiskEngine(oms=mock_oms)
    
    # Test that it was created successfully
    assert risk_engine is not None
    assert risk_engine.oms == mock_oms
    print("✓ RuntimeRiskEngine created successfully")


async def test_runtime_risk_engine_compute_exposure():
    """Test the exposure calculation."""
    print("Testing exposure calculation...")
    
    # Create a mock OMS
    mock_oms = Mock(spec=UnifiedOMS)
    mock_oms.get_pnl.return_value = 1500.0
    
    # Create the risk engine
    risk_engine = RuntimeRiskEngine(oms=mock_oms)
    
    # Create test data
    test_data = pl.DataFrame({
        'close': [100.0, 101.0, 102.0],
        'volume': [1000, 1100, 1200]
    })
    
    # Compute exposure
    result = risk_engine.compute(test_data, risk_metric='exposure')
    
    # Verify results
    assert len(result) == 3
    assert all(val == 1500.0 for val in result.to_list())
    print("✓ Exposure calculation works correctly")


async def test_runtime_risk_engine_compute_drawdown():
    """Test the drawdown calculation (placeholder)."""
    print("Testing drawdown calculation...")
    
    # Create a mock OMS
    mock_oms = Mock(spec=UnifiedOMS)
    mock_oms.get_pnl.return_value = 500.0
    
    # Create the risk engine
    risk_engine = RuntimeRiskEngine(oms=mock_oms)
    
    # Create test data
    test_data = pl.DataFrame({
        'close': [100.0, 101.0, 102.0],
    })
    
    # Compute drawdown
    result = risk_engine.compute(test_data, risk_metric='drawdown')
    
    # Verify results (should be zeros for now)
    assert len(result) == 3
    assert all(val == 0.0 for val in result.to_list())
    print("✓ Drawdown calculation works correctly")


async def test_runtime_risk_engine_factory():
    """Test the factory function."""
    print("Testing factory function...")
    
    # Create a mock OMS
    mock_oms = Mock(spec=UnifiedOMS)
    mock_oms.get_pnl.return_value = 750.0
    
    # Create risk engine using factory
    risk_engine = create_runtime_risk_engine(mock_oms)
    
    # Test that it was created successfully
    assert risk_engine is not None
    assert isinstance(risk_engine, RuntimeRiskEngine)
    assert risk_engine.oms == mock_oms
    print("✓ Factory function works correctly")


async def test_integration_with_OMS():
    """Test integration with OMS-like interface."""
    print("Testing integration with OMS interface...")
    
    # Create a mock OMS that mimics the real interface
    mock_oms = Mock(spec=UnifiedOMS)
    mock_oms.get_pnl.return_value = -250.0  # Simulate a loss
    
    # Create the risk engine
    risk_engine = RuntimeRiskEngine(oms=mock_oms)
    
    # Create test market data
    test_data = pl.DataFrame({
        'timestamp': [1, 2, 3, 4, 5],
        'price': [100.0, 99.0, 98.0, 97.0, 96.0],
    })
    
    # Test different risk metrics
    exposure = risk_engine.compute(test_data, risk_metric='exposure')
    drawdown = risk_engine.compute(test_data, risk_metric='drawdown')
    leverage = risk_engine.compute(test_data, risk_metric='leverage')
    
    # Verify exposure reflects the P&L
    assert all(val == -250.0 for val in exposure.to_list())
    
    # Verify other metrics return expected placeholder values
    assert all(val == 0.0 for val in drawdown.to_list())
    assert all(val == 1.0 for val in leverage.to_list())
    
    print("✓ Integration with OMS interface works correctly")


async def main():
    """Run all tests."""
    print("Running RuntimeRiskEngine tests...\n")
    
    await test_runtime_risk_engine_creation()
    await test_runtime_risk_engine_compute_exposure()
    await test_runtime_risk_engine_compute_drawdown()
    await test_runtime_risk_engine_factory()
    await test_integration_with_OMS()
    
    print("\n✅ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())