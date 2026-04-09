import asyncio
from unittest.mock import MagicMock
import pytest
from qtrader.core.execution_guard import gate_registry, require_initialized
from qtrader.core.system_state import SystemState, state_manager


@pytest.fixture(autouse=True)
def reset_state():
    state_manager.set_state(SystemState.INIT)
    gate_registry._blocked_attempts = 0
    yield


@require_initialized
def dummy_sync_function():
    return "SUCCESS"


@require_initialized
async def dummy_async_function():
    return "SUCCESS"


def test_guard_blocks_in_init():
    state_manager.set_state(SystemState.INIT)
    with pytest.raises(RuntimeError) as exc:
        dummy_sync_function()
    assert "requires INITIALIZED system state" in str(exc.value)
    assert gate_registry._blocked_attempts == 1


@pytest.mark.asyncio
async def test_guard_blocks_async_in_init():
    state_manager.set_state(SystemState.INIT)
    with pytest.raises(RuntimeError) as exc:
        await dummy_async_function()
    assert "requires INITIALIZED system state" in str(exc.value)
    assert gate_registry._blocked_attempts == 1


def test_guard_allows_in_ready():
    state_manager.set_state(SystemState.READY)
    assert dummy_sync_function() == "SUCCESS"
    assert gate_registry._blocked_attempts == 0


@pytest.mark.asyncio
async def test_guard_allows_in_running():
    state_manager.set_state(SystemState.RUNNING)
    assert await dummy_async_function() == "SUCCESS"
    assert gate_registry._blocked_attempts == 0


def test_report_generation():
    state_manager.set_state(SystemState.INIT)
    try:
        dummy_sync_function()
    except RuntimeError:
        pass
    import json

    with open("qtrader/audit/guard_report.json") as f:
        report = json.load(f)
    assert report["blocked_attempts"] > 0
    assert report["status"] == "GUARD_ACTIVE"
    assert report["system_state"] == "INIT"
