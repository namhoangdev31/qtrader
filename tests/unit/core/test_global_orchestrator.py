import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from qtrader.core.global_orchestrator import GlobalOrchestrator, FundMode

@pytest.fixture
def mock_orchestrator():
    orch = MagicMock()
    # Mock some components to avoid attribute errors
    orch.network_kill_switch = AsyncMock()
    orch.portfolio_allocator = MagicMock()
    orch.state_store = AsyncMock()
    orch.run = AsyncMock()
    return orch

@pytest.fixture
def global_orchestrator():
    return GlobalOrchestrator()

def test_register_orchestrator(global_orchestrator, mock_orchestrator):
    global_orchestrator.register_orchestrator("test_orch", mock_orchestrator)
    assert "test_orch" in global_orchestrator._orchestrators

def test_set_fund_mode(global_orchestrator):
    global_orchestrator.set_fund_mode("LIVE")
    assert global_orchestrator._mode == FundMode.LIVE
    
    global_orchestrator.set_fund_mode("SHADOW")
    assert global_orchestrator._mode == FundMode.SHADOW

@pytest.mark.asyncio
async def test_global_kill_switch(global_orchestrator, mock_orchestrator):
    global_orchestrator.register_orchestrator("orch1", mock_orchestrator)
    global_orchestrator.register_orchestrator("orch2", mock_orchestrator)
    
    await global_orchestrator.engage_global_kill_switch("Emergency")
    
    assert global_orchestrator._kill_switch_active
    # Verify child kill switch was called
    assert mock_orchestrator.network_kill_switch.engage_hard_kill.call_count == 2
    
@pytest.mark.asyncio
async def test_run_fund_allocation(global_orchestrator, mock_orchestrator):
    global_orchestrator.register_orchestrator("orch1", mock_orchestrator)
    
    # Mocking set_risk_multiplier
    mock_orch_allocator = mock_orchestrator.portfolio_allocator
    mock_orch_allocator.set_risk_multiplier = MagicMock()
    
    await global_orchestrator.run_fund_allocation()
    
    # 1 strategy should have multiplier ~1.0 if weights are balanced
    assert mock_orch_allocator.set_risk_multiplier.called

@pytest.mark.asyncio
async def test_get_total_fund_risk(global_orchestrator, mock_orchestrator):
    global_orchestrator.register_orchestrator("orch1", mock_orchestrator)
    
    # Mock positions
    from qtrader.core.state_store import Position
    from decimal import Decimal
    mock_orchestrator.state_store.get_positions.return_value = {
        "BTC": Position(symbol="BTC", quantity=Decimal("1.0"), average_price=Decimal("50000"))
    }
    
    risk = await global_orchestrator.get_total_fund_risk()
    assert risk["total_assets"] == 1
    assert risk["num_strategies"] == 1
