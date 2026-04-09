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
    await engine.handle_error("ExecutionUnit", FatalError("State corruption!"))
    mock_orchestrator.engage_global_kill_switch.assert_called_once()
    assert engine.halt_count == 1
    assert engine.trigger_count == 1


@pytest.mark.asyncio
async def test_fail_fast_escalation(mock_orchestrator):
    engine = FailFastEngine(global_orchestrator=mock_orchestrator, max_retries=2)
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))
    assert mock_orchestrator.engage_global_kill_switch.call_count == 0
    await engine.handle_error("BinanceData", RecoverableError("Timeout"))
    assert mock_orchestrator.engage_global_kill_switch.call_count == 0
    assert engine.trigger_count == 3


@pytest.mark.asyncio
async def test_fail_fast_unknown_error_escalation(mock_orchestrator):
    engine = FailFastEngine(global_orchestrator=mock_orchestrator)
    await engine.handle_error("OMS", ValueError("Unexpected nil value"))
    mock_orchestrator.engage_global_kill_switch.assert_called_once()
    assert engine.halt_count == 1
