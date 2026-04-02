from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qtrader.core.orchestrator import TradingOrchestrator
from qtrader.core.system_state import SystemState, state_manager


@pytest.fixture
def orchestrator_deps():
    """Mocks for Orchestrator dependencies."""
    return {
        "event_bus": MagicMock(),
        "market_data_adapter": MagicMock(),
        "alpha_modules": [],
        "feature_validator": MagicMock(),
        "strategies": [],
        "ensemble_strategy": MagicMock(),
        "portfolio_allocator": MagicMock(),
        "runtime_risk_engine": MagicMock(),
        "oms_adapter": MagicMock(),
    }

@pytest.mark.asyncio
async def test_orchestrator_initialization_blocked_by_precheck(orchestrator_deps):
    """Orchestrator should raise RuntimeError if PreExecutionValidator fails."""
    # Reset state
    state_manager.set_state(SystemState.INIT)
    
    with patch("qtrader.core.orchestrator.PreExecutionValidator") as validator_cls:
        validator = MagicMock()
        validator.validate.return_value = False # FAIL
        validator_cls.return_value = validator
        
        # We need to mock other things that TradingOrchestrator.__init__ might use
        with patch("qtrader.core.orchestrator.container") as mock_container, \
             patch("qtrader.core.orchestrator.FileEventStore"), \
             patch("qtrader.core.orchestrator.ShadowEngine"), \
             patch("qtrader.core.orchestrator.ResourceMonitor"), \
             patch("qtrader.core.orchestrator.NetworkKillSwitch"), \
             patch("qtrader.core.orchestrator.settings") as mock_settings:
            
            mock_settings.TRADING_SYMBOLS = ["BTC/USDT"]
            
            # Setup container mocks
            def get_side_effect(k):
                m = MagicMock()
                if k == "config":
                    m.update = AsyncMock()
                return m
            mock_container.get.side_effect = get_side_effect
            
            orchestrator = TradingOrchestrator(**orchestrator_deps)
            orchestrator.seed_manager = MagicMock()
            orchestrator.seed_manager.is_applied.return_value = True
            orchestrator.trace_authority = MagicMock()
            orchestrator.settings = MagicMock()
            
            with pytest.raises(RuntimeError, match="System pre-execution validation failed"):
                orchestrator.initialize()
            
            assert validator.validate.called
            assert state_manager.state == SystemState.ERROR

@pytest.mark.asyncio
async def test_orchestrator_initialization_success(orchestrator_deps):
    """Orchestrator should proceed if PreExecutionValidator passes."""
    state_manager.set_state(SystemState.INIT)
    
    with patch("qtrader.core.orchestrator.PreExecutionValidator") as validator_cls:
        validator = MagicMock()
        validator.validate.return_value = True # PASS
        validator_cls.return_value = validator
        
        with patch("qtrader.core.orchestrator.container") as mock_container, \
             patch("qtrader.core.orchestrator.FileEventStore"), \
             patch("qtrader.core.orchestrator.ShadowEngine"), \
             patch("qtrader.core.orchestrator.ResourceMonitor"), \
             patch("qtrader.core.orchestrator.NetworkKillSwitch"), \
             patch("qtrader.core.orchestrator.settings") as mock_settings:
            
            mock_settings.TRADING_SYMBOLS = ["BTC/USDT"]
            def get_side_effect(k):
                m = MagicMock()
                if k == "config":
                    m.update = AsyncMock()
                return m
            mock_container.get.side_effect = get_side_effect
            
            orchestrator = TradingOrchestrator(**orchestrator_deps)
            orchestrator.seed_manager = MagicMock()
            orchestrator.seed_manager.is_applied.return_value = True
            orchestrator.trace_authority = MagicMock()
            orchestrator.settings = MagicMock()
            
            # Since recover_state is an async task, we should mock it or be careful
            with patch.object(TradingOrchestrator, "recover_state", side_effect=lambda: AsyncMock()()):
                orchestrator.initialize()
                
            assert validator.validate.called
            assert state_manager.state == SystemState.READY
