import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from qtrader.core.event_bus import EventBus
from qtrader.core.types import EventType

@pytest.fixture
def logger_mock():
    return MagicMock()

@pytest.fixture
def event_bus(logger_mock):
    return EventBus(logger=logger_mock)

@pytest.mark.asyncio
async def test_event_bus_start_stop(event_bus):
    await event_bus.start()
    assert event_bus._running is True
    assert event_bus._task is not None
    
    await event_bus.stop()
    assert event_bus._running is False

@pytest.mark.asyncio
async def test_event_bus_publish_subscribe(event_bus):
    future = asyncio.Future()
    
    def callback(data):
        future.set_result(data)
    
    event_bus.subscribe(EventType.SYSTEM, callback)
    await event_bus.start()
    
    test_data = {"msg": "hello"}
    await event_bus.publish(EventType.SYSTEM, test_data)
    
    result = await asyncio.wait_for(future, timeout=1.0)
    assert result == test_data
    await event_bus.stop()

@pytest.mark.asyncio
async def test_event_bus_unsubscribe(event_bus):
    mock_callback = MagicMock()
    
    event_bus.subscribe(EventType.SYSTEM, mock_callback)
    event_bus.unsubscribe(EventType.SYSTEM, mock_callback)
    
    await event_bus.start()
    await event_bus.publish(EventType.SYSTEM, {"msg": "hello"})
    
    # Wait a bit to ensure potential processing
    await asyncio.sleep(0.1)
    
    mock_callback.assert_not_called()
    await event_bus.stop()

@pytest.mark.asyncio
async def test_event_bus_retry_logic(logger_mock):
    # Create event bus with small retry delay for faster test
    bus = EventBus(logger=logger_mock, max_retries=2, base_retry_delay=0.01)
    
    fail_count = 0
    future = asyncio.Future()
    
    def failing_callback(data):
        nonlocal fail_count
        fail_count += 1
        if fail_count <= 2:
            raise ValueError("Intentional failure")
        future.set_result("success以后")

    bus.subscribe(EventType.SYSTEM, failing_callback)
    await bus.start()
    await bus.publish(EventType.SYSTEM, "test")
    
    result = await asyncio.wait_for(future, timeout=1.0)
    assert result == "success以后"
    assert fail_count == 3
    await bus.stop()

@pytest.mark.asyncio
async def test_event_bus_dead_letter_queue(logger_mock):
    bus = EventBus(logger=logger_mock, max_retries=1, base_retry_delay=0.01)
    
    def always_fail(data):
        raise ValueError("Permanent failure")
        
    bus.subscribe(EventType.SYSTEM, always_fail)
    await bus.start()
    await bus.publish(EventType.SYSTEM, "fail_test")
    
    # Wait for retries to exhaust
    await asyncio.sleep(0.2)
    
    metrics = bus.get_metrics()
    assert metrics["events_failed"] == 1
    assert metrics["dead_letter_count"] == 1
    
    dead_letters = await bus.get_dead_letters()
    assert len(dead_letters) == 1
    assert dead_letters[0]["event_type"] == EventType.SYSTEM
    assert dead_letters[0]["data"] == "fail_test"
    
    await bus.stop()
