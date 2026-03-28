import asyncio
import pytest
import time
from qtrader.core.concurrency_guard import ConcurrencyGuard, concurrency_guard, safe_update

@pytest.mark.asyncio
async def test_concurrency_guard_serialization():
    # Simulate a shared resource with parallel updates
    shared_state = {"counter": 0}
    
    async def increment_task():
        # Without lock, this would race
        async def _inc():
            current = shared_state["counter"]
            await asyncio.sleep(0.01) # Force context switch
            shared_state["counter"] = current + 1
            
        await safe_update("counter_resource", _inc())
        
    # Spawn 10 parallel increments
    await asyncio.gather(*(increment_task() for _ in range(10)))
    
    # Assert perfectly serialized execution (10 increments = 10 total)
    assert shared_state["counter"] == 10

from io import StringIO
from loguru import logger

@pytest.mark.asyncio
async def test_concurrency_guard_deadlock_detection_metrics():
    # Capture loguru output
    output = StringIO()
    handler_id = logger.add(output, format="{message}")
    
    try:
        async def slow_task():
            # Hold lock for 60ms (limit is 50ms)
            await asyncio.sleep(0.06)
            
        # Acquire lock manually and hold it correctly
        await concurrency_guard.acquire("slow_resource")
        await slow_task()
        concurrency_guard.release("slow_resource")
        
        # Verify budget breach log
        log_content = output.getvalue()
        assert "Budget Breach: Resource='slow_resource' held for" in log_content
    finally:
        logger.remove(handler_id)

@pytest.mark.asyncio
async def test_concurrency_guard_error_resiliency():
    # Ensure lock is released even if the coroutine fails
    async def failing_task():
        raise ValueError("Simulated failure inside lock")
        
    with pytest.raises(ValueError):
        await safe_update("error_resource", failing_task())
        
    # Assert lock is released and can be re-acquired immediately
    await asyncio.wait_for(concurrency_guard.acquire("error_resource"), timeout=0.1)
    concurrency_guard.release("error_resource")
