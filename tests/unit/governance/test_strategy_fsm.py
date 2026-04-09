from unittest.mock import AsyncMock, patch
import pytest
from qtrader.core.events import EventType
from qtrader.governance.strategy_fsm import StrategyFSM

STRATEGY_A = "ALGO_MOMENTUM_BTC"


@pytest.mark.asyncio
async def test_strategy_fsm_successful_lifecycle() -> None:
    bus = AsyncMock()
    fsm = StrategyFSM(bus)
    success = await fsm.transition(STRATEGY_A, StrategyFSM.SANDBOX)
    assert success
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.SANDBOX
    assert bus.publish.called
    await fsm.transition(STRATEGY_A, StrategyFSM.APPROVED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.APPROVED
    await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    assert fsm.is_active(STRATEGY_A)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.ACTIVE
    await fsm.transition(STRATEGY_A, StrategyFSM.PAUSED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.PAUSED
    assert not fsm.is_active(STRATEGY_A)
    await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    assert fsm.is_active(STRATEGY_A)
    await fsm.transition(STRATEGY_A, StrategyFSM.KILLED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.KILLED


@pytest.mark.asyncio
async def test_strategy_fsm_forbidden_transitions() -> None:
    bus = AsyncMock()
    fsm = StrategyFSM(bus)
    success = await fsm.transition(STRATEGY_A, StrategyFSM.APPROVED)
    assert not success
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.INIT
    assert bus.publish.call_args[0][0].event_type == EventType.FSM_ERROR
    await fsm.transition(STRATEGY_A, StrategyFSM.SANDBOX)
    await fsm.transition(STRATEGY_A, StrategyFSM.APPROVED)
    await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    await fsm.transition(STRATEGY_A, StrategyFSM.KILLED)
    bus.reset_mock()
    success = await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    assert not success
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.KILLED
    assert bus.publish.call_args[0][0].event_type == EventType.FSM_ERROR


@pytest.mark.asyncio
async def test_strategy_fsm_system_failure() -> None:
    bus = AsyncMock()
    fsm = StrategyFSM(bus)
    with patch.object(fsm, "_allowed_transitions", new=None):
        success = await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
        assert not success
        assert bus.publish.called
        assert bus.publish.call_args[0][0].event_type == EventType.FSM_ERROR
        assert bus.publish.call_args[0][0].payload.error_type == "SYSTEM_FAILURE"
    with patch.object(fsm, "_emit_fsm_error", side_effect=Exception("CRITICAL")):
        with patch.object(fsm, "_allowed_transitions", new=None):
            success = await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
            assert not success
