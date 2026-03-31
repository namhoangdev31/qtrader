import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from qtrader.core.orchestrator import TradingOrchestrator, SystemState
from qtrader.core.events import EventType
from qtrader.core.types import MarketData

@pytest.fixture
def orchestrator_mock():
    event_bus = AsyncMock()
    market_data_adapter = MagicMock()
    alpha_modules = [AsyncMock()]
    feature_validator = AsyncMock()
    strategies = [AsyncMock()]
    ensemble_strategy = AsyncMock()
    portfolio_allocator = AsyncMock()
    runtime_risk_engine = AsyncMock()
    oms_adapter = AsyncMock()
    state_store = AsyncMock()
    
    # Correct constructor for TradingOrchestrator
    # Note: Using required arguments as per earlier viewed constructor
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
    return orchestrator

@pytest.mark.asyncio
async def test_pipeline_propagation_sequence(orchestrator_mock):
    """
    Verify the 1-to-2 stage propagation: 
    MarketData -> Feature Validation.
    """
    # 1. Mock market data
    market_data = MarketData(
        symbol="BTC/USDT",
        timestamp=0,
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0
    )
    
    # 2. Trigger Stage 1 (Market)
    # Ensure orchestrator is RUNNING to allow execution
    from qtrader.core.system_state import state_manager
    state_manager.set_state(SystemState.RUNNING)
    
    await orchestrator_mock.handle_market_data(market_data)
    
    # 3. Assert Stage 2 (Feature) was published
    orchestrator_mock.event_bus.publish.assert_any_call(
        EventType.FEATURES, 
        pytest.any(dict)
    )

@pytest.mark.asyncio
async def test_bypass_prevention(orchestrator_mock):
    """
    Verify that Feature handler correctly publishes to ValidatedFeatures stage.
    """
    # 1. Mock features
    features_data = {
        "features": {"alpha_1": 0.5},
        "trace_id": "test_trace"
    }
    
    # 2. Trigger Stage 2 (Feature)
    # Mocking the validator response
    orchestrator_mock.feature_validator.validate = AsyncMock(return_value=MagicMock(features={"alpha_1": 0.5}))
    
    await orchestrator_mock.handle_features(features_data)
    
    # 3. Assert Stage 3 (Validated Features) was published
    orchestrator_mock.event_bus.publish.assert_any_call(
        EventType.VALIDATED_FEATURES, 
        pytest.any(dict)
    )
