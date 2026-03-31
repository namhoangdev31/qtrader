import pytest
import asyncio
from unittest.mock import MagicMock
from qtrader.core.system_state import state_manager, SystemState
from qtrader.core.execution_guard import require_initialized, gate_registry

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
    """Verify that execution is blocked in INIT state."""
    state_manager.set_state(SystemState.INIT)
    
    with pytest.raises(RuntimeError) as exc:
        dummy_sync_function()
    assert "requires INITIALIZED system state" in str(exc.value)
    assert gate_registry._blocked_attempts == 1

@pytest.mark.asyncio
async def test_guard_blocks_async_in_init():
    """Verify that async execution is blocked in INIT state."""
    state_manager.set_state(SystemState.INIT)
    
    with pytest.raises(RuntimeError) as exc:
        await dummy_async_function()
    assert "requires INITIALIZED system state" in str(exc.value)
    assert gate_registry._blocked_attempts == 1

def test_guard_allows_in_ready():
    """Verify that execution is allowed in READY state."""
    state_manager.set_state(SystemState.READY)
    assert dummy_sync_function() == "SUCCESS"
    assert gate_registry._blocked_attempts == 0

@pytest.mark.asyncio
async def test_guard_allows_in_running():
    """Verify that execution is allowed in RUNNING state."""
    state_manager.set_state(SystemState.RUNNING)
    assert await dummy_async_function() == "SUCCESS"
    assert gate_registry._blocked_attempts == 0

def test_report_generation():
    """Verify that guard_report.json is correctly updated."""
    state_manager.set_state(SystemState.INIT)
    try:
        dummy_sync_function()
    except RuntimeError:
        pass
    
    import json
    with open("qtrader/audit/guard_report.json", "r") as f:
        report = json.load(f)
    
    assert report["blocked_attempts"] > 0
    assert report["status"] == "GUARD_ACTIVE"
    assert report["system_state"] == "INIT"
