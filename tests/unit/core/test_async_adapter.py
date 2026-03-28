import asyncio
import aiohttp
import pytest
from qtrader.core.async_adapter import AsyncAdapter, async_authority, get_session, spawn_task

@pytest.mark.asyncio
async def test_async_adapter_singleton_session():
    # 1. Obtain shared session
    session1 = await get_session()
    session2 = await get_session()
    
    # 2. Assert singleton behavior
    assert session1 is session2
    assert isinstance(session1, aiohttp.ClientSession)
    assert not session1.closed
    
    # 3. Cleanup for tests
    await async_authority.close()
    assert session1.closed

@pytest.mark.asyncio
async def test_async_adapter_run_task_success():
    async def fast_task():
        await asyncio.sleep(0.01)
        return "SUCCESS"
        
    res = await AsyncAdapter.run_task(fast_task())
    assert res == "SUCCESS"

@pytest.mark.asyncio
async def test_async_adapter_run_task_failure():
    async def failing_task():
        raise ValueError("Simulated Async Failure")
    
    # Verify error callback handling
    mock_error_cb = MagicMock()
    res = await AsyncAdapter.run_task(failing_task(), on_error=mock_error_cb)
    
    assert res is None
    mock_error_cb.assert_called_once()


from unittest.mock import MagicMock

@pytest.mark.asyncio
async def test_async_adapter_background_task_done_callback():
    # Fire and forget background task
    success_flag = False
    
    async def bg_task():
        nonlocal success_flag
        await asyncio.sleep(0.01)
        success_flag = True
        
    task = spawn_task(bg_task())
    
    # Wait for background task to finish in test context
    await task
    assert success_flag is True
