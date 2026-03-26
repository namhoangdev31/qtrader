import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from qtrader.core.event import EventType, NormalizedTimestampEvent
from qtrader.data.market.clock_sync import ClockSync
from qtrader.oms.event_store import EventStore
from qtrader.core.event_bus import EventBus

@pytest.fixture
def mock_store():
    store = MagicMock()
    store.record_event = AsyncMock()
    return store

@pytest.fixture
def mock_bus():
    bus = MagicMock()
    bus.publish = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_clock_sync_offset_calculation(mock_store, mock_bus):
    sync = ClockSync(event_store=mock_store, event_bus=mock_bus, update_interval=100)
    
    # Mock offset to 1.5ms
    sync._get_ntp_offset = AsyncMock(return_value=1.5)
    
    offset = await sync.update_offset()
    assert offset == 1.5
    assert sync._offset_ms == 1.5
    
    # Verify NormalizedTimestampEvent recorded
    mock_store.record_event.assert_called_once()
    mock_bus.publish.called
    sync_call = mock_bus.publish.call_args_list[0]
    assert sync_call.args[0] == EventType.CLOCK_SYNC
    assert isinstance(sync_call.args[1], NormalizedTimestampEvent)

@pytest.mark.asyncio
async def test_clock_sync_normalization(mock_store, mock_bus):
    sync = ClockSync(event_store=mock_store, event_bus=mock_bus)
    sync._offset_ms = 10.0 # 10ms offset
    
    raw_ts = 1700000000.0
    event = {
        "timestamp": raw_ts,
        "symbol": "BTC-USDT"
    }
    
    result = await sync.handle(event)
    
    # Normalized timestamp should be raw_ts + 10ms
    assert result["normalized_timestamp"] == raw_ts + 0.010
    assert result["clock_offset_ms"] == 10.0

@pytest.mark.asyncio
async def test_clock_sync_fallback(mock_store, mock_bus):
    sync = ClockSync(event_store=mock_store, event_bus=mock_bus)
    sync._offset_ms = 5.0 # Pre-existing offset
    
    # Mock sync failure
    sync._get_ntp_offset = AsyncMock(side_effect=Exception("Timeout"))
    
    offset = await sync.update_offset()
    
    # Should fallback to last known offset
    assert offset == 5.0
    assert sync._offset_ms == 5.0
