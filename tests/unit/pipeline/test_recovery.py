from unittest.mock import AsyncMock, MagicMock

import pytest

from qtrader.core.event import EventType, GapFreeMarketEvent, RecoveryCompletedEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.market.snapshot_recovery import RecoveryEngine
from qtrader.data.pipeline.recovery import RecoveryService


@pytest.fixture
def mock_engine():
    engine = MagicMock(spec=RecoveryEngine)
    engine.recover = AsyncMock()
    return engine

@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus

@pytest.mark.asyncio
async def test_recovery_service_normal_pass(mock_engine, mock_bus):
    service = RecoveryService(recovery_engine=mock_engine, event_bus=mock_bus)
    
    # Normal event with no recovery required
    event = {"symbol": "BTC-USDT", "seq_id": 101, "metadata": {}}
    result = await service.handle(event)
    
    assert result == event
    mock_engine.recover.assert_not_called()

@pytest.mark.asyncio
async def test_recovery_service_with_recovery_trigger(mock_engine, mock_bus):
    service = RecoveryService(recovery_engine=mock_engine, event_bus=mock_bus)
    
    # Event with gap_detected = True
    event = {
        "symbol": "BTC-USDT", 
        "seq_id": 105, 
        "metadata": {
            "gap_detected": True,
            "expected_seq": 101,
            "received_seq": 105
        }
    }
    
    # Mock successful recovery
    mock_gap_free_event = MagicMock(spec=GapFreeMarketEvent)
    mock_gap_free_event.seq_id = 105
    mock_engine.recover.return_value = mock_gap_free_event
    
    result = await service.handle(event)
    
    # Recovery should return the event with metadata updated
    assert result["metadata"]["gap_free_event"] == mock_gap_free_event
    
    # Should publish recovery completed event
    mock_engine.recover.assert_called_once_with("BTC-USDT", 101, 105)
    
    # Second call for publish (RecoveryCompletedEvent)
    assert mock_bus.publish.called
    sync_call = mock_bus.publish.call_args_list[0]
    assert sync_call.args[0] == EventType.RECOVERY_COMPLETED
    assert isinstance(sync_call.args[1], RecoveryCompletedEvent)

@pytest.mark.asyncio
async def test_recovery_service_failure(mock_engine, mock_bus):
    service = RecoveryService(recovery_engine=mock_engine, event_bus=mock_bus)
    
    event = {"symbol": "BTC-USDT", "seq_id": 105, "metadata": {"gap_detected": True}}
    
    # Mock recovery failure
    mock_engine.recover.return_value = None
    
    result = await service.handle(event)
    
    # Pipeline should be blocked on recovery failure
    assert result is None
