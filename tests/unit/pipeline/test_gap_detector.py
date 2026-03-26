import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from qtrader.core.event import EventType, MarketDataEvent, GapDetectedEvent
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.oms.event_store import EventStore
from qtrader.core.event_bus import EventBus

@pytest.fixture
def mock_store():
    store = MagicMock(spec=EventStore)
    store.get_last_sequence.return_value = 100
    return store

@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_gap_detector_no_gap(mock_store, mock_bus):
    detector = GapDetector(event_store=mock_store, event_bus=mock_bus)
    
    # Expected is 101, receive 101
    event = {
        "symbol": "BTC-USDT",
        "seq_id": 101,
        "trace_id": "trace-1"
    }
    
    result = await detector.handle(event)
    assert result == event
    mock_bus.publish.assert_not_called()

@pytest.mark.asyncio
async def test_gap_detector_with_gap(mock_store, mock_bus):
    detector = GapDetector(event_store=mock_store, event_bus=mock_bus)
    
    # Expected is 101, receive 105
    event = {
        "symbol": "BTC-USDT",
        "seq_id": 105,
        "trace_id": "trace-gap"
    }
    
    result = await detector.handle(event)
    
    # On gap, should tag the event for recovery and publish GapDetectedEvent
    assert result["metadata"]["gap_detected"] is True
    assert result["metadata"]["expected_seq"] == 101
    assert result["metadata"]["received_seq"] == 105
    
    assert mock_bus.publish.called
    call_args = mock_bus.publish.call_args_list[0]
    assert call_args.args[0] == EventType.GAP_DETECTED
    assert isinstance(call_args.args[1], GapDetectedEvent)
    assert call_args.args[1].expected_seq == 101
    assert call_args.args[1].received_seq == 105

@pytest.mark.asyncio
async def test_gap_detector_stateless_per_symbol(mock_store, mock_bus):
    detector = GapDetector(event_store=mock_store, event_bus=mock_bus)
    
    # ETH-USDT has last_seq = 0
    mock_store.get_last_sequence.side_effect = lambda symbol: 100 if symbol == "BTC-USDT" else 0
    
    # BTC-USDT (No gap)
    event_btc = {"symbol": "BTC-USDT", "seq_id": 101}
    await detector.handle(event_btc)
    
    # ETH-USDT (No gap, start from 1)
    event_eth = {"symbol": "ETH-USDT", "seq_id": 1}
    result_eth = await detector.handle(event_eth)
    
    assert result_eth == event_eth
    assert "metadata" not in result_eth or not result_eth["metadata"].get("recovery_required")
