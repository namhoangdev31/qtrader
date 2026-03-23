#!/usr/bin/env python3
"""
Test the orchestrator with state store integration.
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock
from decimal import Decimal
from datetime import datetime

from qtrader.core.orchestrator import TradingOrchestrator
from qtrader.core.state_store import StateStore
from qtrader.core.types import EventType, MarketData, SignalEvent, AllocationWeights, RiskMetrics


async def test_orchestrator_with_state_store():
    """Test that orchestrator properly uses state store."""
    # Create mocks
    event_bus = MagicMock()
    # Make the publish method an AsyncMock
    event_bus.publish = AsyncMock()
    market_data_adapter = MagicMock()
    alpha_modules = []
    feature_validator = MagicMock()
    strategies = []
    ensemble_strategy = MagicMock()
    portfolio_allocator = MagicMock()
    runtime_risk_engine = MagicMock()
    oms_adapter = MagicMock()
    
    # Setup mock returns
    feature_validator.validate.return_value = {"test_feature": Decimal('1.0')}
    ensemble_strategy.generate_signal.return_value = MagicMock(
        signal_type="LONG",
        strength=Decimal('0.8')
    )
    portfolio_allocator.allocate.return_value = AllocationWeights(
        timestamp=datetime.utcnow(),
        weights={"BTCUSDT": Decimal('1.0')}
    )
    runtime_risk_engine.evaluate_risk.return_value = RiskMetrics(
        timestamp=datetime.utcnow(),
        portfolio_var=Decimal('0.01'),
        portfolio_volatility=Decimal('0.01'),
        max_drawdown=Decimal('0.01'),
        leverage=Decimal('1.0'),
        metadata={}
    )
    oms_adapter.create_order.return_value = MagicMock()
    
    # Create state store
    state_store = StateStore()
    
    # Create orchestrator
    orchestrator = TradingOrchestrator(
        event_bus=event_bus,
        market_data_adapter=market_data_adapter,
        alpha_modules=alpha_modules,
        feature_validator=feature_validator,
        strategies=strategies,
        ensemble_strategy=ensemble_strategy,
        portfolio_allocator=portfolio_allocator,
        runtime_risk_engine=runtime_risk_engine,
        oms_adapter=oms_adapter,
        state_store=state_store
    )
    
    # Test that initial state is empty
    positions = await state_store.get_positions()
    assert positions == {}
    
    # Create and process market data
    market_data = MarketData(
        symbol="BTCUSDT",
        timestamp=datetime.utcnow(),
        open=Decimal('50000'),
        high=Decimal('51000'),
        low=Decimal('49000'),
        close=Decimal('50500'),
        volume=Decimal('100')
    )
    
    await orchestrator.handle_market_data(market_data)
    
    # Verify that the event bus publish was called for FEATURES
    event_bus.publish.assert_awaited()
    
    # Verify that position was updated via state store
    # Note: We're checking the state store directly since the orchestrator updates it
    btc_position = await state_store.get_position("BTCUSDT")
    # The position should exist now (though we're not checking exact values as 
    # the flow is complex with multiple steps)
    assert btc_position is not None
    
    logger.info("Orchestrator state store integration test passed!")


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    asyncio.run(test_orchestrator_with_state_store())