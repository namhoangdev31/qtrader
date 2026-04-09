import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.errors import CriticalError, FatalError, RecoverableError
from qtrader.core.fail_fast_engine import FailFastEngine


@pytest.fixture
def mock_orchestrator():
    orchestrator = MagicMock()
    orchestrator.engage_global_kill_switch = AsyncMock()
    return orchestrator


@pytest.mark.asyncio
async def test_fail_fast_halt_on_fatal(mock_orchestrator):
    engine = FailFastEngine(global_orchestrator=mock_orchestrator)

    # 1. Trigger a FatalError
    await engine.handle_error("ExecutionUnit", FatalError("State corruption!"))

    # 2. Verify kill switch call
    mock_orchestrator.engage_global_kill_switch.assert_called_once()
    assert engine.halt_count == 1
    assert engine.trigger_count == 1


@pytest.mark.asyncio
async def test_fail_fast_escalation(mock_orchestrator):
    # Set low retry threshold for testing
    engine = FailFastEngine(global_orchestrator=mock_orchestrator, max_retries=2)

    # 1. First 2 retries (should be Recoverable)
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))
    assert mock_orchestrator.engage_global_kill_switch.call_count == 0

    # 2. 3rd occurrence (should ESCALATE to CriticalError)
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))

    # Currently, isolation calls aren't mocked, but we should verify it doesn't halt yet
    # (Since severity of CriticalError is 2, not >= 3)
    assert mock_orchestrator.engage_global_kill_switch.call_count == 0
    assert engine.trigger_count == 3


@pytest.mark.asyncio
async def test_fail_fast_unknown_error_escalation(mock_orchestrator):
    engine = FailFastEngine(global_orchestrator=mock_orchestrator)

    # 1. Handle an unknown exception
    await engine.handle_error("OMS", ValueError("Unexpected nil value"))

    # 2. Verify it's treated as Fatal and halts
    mock_orchestrator.engage_global_kill_switch.assert_called_once()
    assert engine.halt_count == 1
