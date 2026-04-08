from unittest.mock import AsyncMock, patch

import pytest

from qtrader.core.events import EventType
from qtrader.governance.strategy_fsm import StrategyFSM

# Test Constants
STRATEGY_A = "ALGO_MOMENTUM_BTC"


@pytest.mark.asyncio
async def test_strategy_fsm_successful_lifecycle() -> None:
    """Verify that a strategy can strictly follow the entire lifecycle path."""
    bus = AsyncMock()
    fsm = StrategyFSM(bus)

    # 1. INIT -> SANDBOX
    success = await fsm.transition(STRATEGY_A, StrategyFSM.SANDBOX)
    assert success
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.SANDBOX
    assert bus.publish.called

    # 2. SANDBOX -> APPROVED
    await fsm.transition(STRATEGY_A, StrategyFSM.APPROVED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.APPROVED

    # 3. APPROVED -> ACTIVE
    await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    assert fsm.is_active(STRATEGY_A)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.ACTIVE

    # 4. ACTIVE <-> PAUSED
    await fsm.transition(STRATEGY_A, StrategyFSM.PAUSED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.PAUSED
    assert not fsm.is_active(STRATEGY_A)

    await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
    assert fsm.is_active(STRATEGY_A)

    # 5. ACTIVE -> KILLED (Terminal)
    await fsm.transition(STRATEGY_A, StrategyFSM.KILLED)
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.KILLED


@pytest.mark.asyncio
async def test_strategy_fsm_forbidden_transitions() -> None:
    """Verify that the FSM strictly blocks and emits errors for forbidden transitions."""
    bus = AsyncMock()
    fsm = StrategyFSM(bus)

    # Case 1: Trigger INIT -> APPROVED (Forbidden, must go through SANDBOX)
    success = await fsm.transition(STRATEGY_A, StrategyFSM.APPROVED)
    assert not success
    assert fsm.get_state(STRATEGY_A) == StrategyFSM.INIT
    assert bus.publish.call_args[0][0].event_type == EventType.FSM_ERROR

    # Case 2: Trigger KILLED -> ACTIVE (Forbidden, terminal state)
    # Move to KILLED first
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
    """Verify industrial error handling during system-level exceptions."""
    bus = AsyncMock()
    fsm = StrategyFSM(bus)

    # 1. Trigger Exception in transition (using mock to force failure before validation)
    # Patch self._allowed_transitions to force a crash during lookup
    with patch.object(fsm, "_allowed_transitions", new=None):
        success = await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
        assert not success
        assert bus.publish.called
        assert bus.publish.call_args[0][0].event_type == EventType.FSM_ERROR
        assert bus.publish.call_args[0][0].payload.error_type == "SYSTEM_FAILURE"

    # 2. Trigger Nested Exception (Recovery failure)
    # Patch _emit_fsm_error to crash during recovery
    with patch.object(fsm, "_emit_fsm_error", side_effect=Exception("CRITICAL")):
        with patch.object(fsm, "_allowed_transitions", new=None):
            success = await fsm.transition(STRATEGY_A, StrategyFSM.ACTIVE)
            assert not success
            # Recovery failed, so bus.publish won't be called for the error event
