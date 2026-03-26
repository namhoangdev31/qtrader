import pytest
from unittest.mock import AsyncMock, MagicMock
from qtrader.core.event import EventType, MarketDataEvent, GapFreeMarketEvent
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.oms.event_store import EventStore
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.base import DataNormalizer
from qtrader.data.pipeline.arbitrator import Arbitrator
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.data.pipeline.recovery import RecoveryService
from qtrader.data.market.clock_sync import ClockSync
from qtrader.data.quality_gate import DataQualityGate

@pytest.fixture
def mock_store():
    store = MagicMock(spec=EventStore)
    store.get_last_sequence.return_value = 0
    store.get_recent_prices.return_value = [50000.0] * 50
    store.get_latest_price_cross_exchange.return_value = 50000.0
    store.record_event = AsyncMock()
    return store

@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=EventBus)
    bus.publish = AsyncMock()
    return bus

@pytest.fixture
def mock_normalizer():
    norm = MagicMock(spec=DataNormalizer)
    
    def fake_normalize(data):
        # Return a MarketDataEvent instead of a dict
        return MarketDataEvent(
            symbol=data["symbol"],
            data={"last_price": 50000.0},
            metadata={"venue": data["venue"]},
            trace_id="t-1"
        )
    
    norm.normalize.side_effect = fake_normalize
    return norm

@pytest.fixture
def orchestrator(mock_bus, mock_store, mock_normalizer):
    # Mock all internal stages to avoid deep nesting
    clock_sync = MagicMock(spec=ClockSync)
    clock_sync.handle = AsyncMock(side_effect=lambda x: x)
    clock_sync.start = AsyncMock()
    clock_sync.stop = AsyncMock()
    
    arbitrator = MagicMock(spec=Arbitrator)
    arbitrator.handle.side_effect = lambda x: x
    
    gap_detector = MagicMock(spec=GapDetector)
    gap_detector.handle = AsyncMock(side_effect=lambda x: x)
    
    recovery = MagicMock(spec=RecoveryService)
    recovery.handle = AsyncMock(side_effect=lambda x: x)
    
    quality_gate = MagicMock(spec=DataQualityGate)
    quality_gate.validate.return_value = True
    
    return MarketPipelineOrchestrator(
        event_bus=mock_bus,
        event_store=mock_store,
        normalizer=mock_normalizer,
        arbitrator=arbitrator,
        clock_sync=clock_sync,
        gap_detector=gap_detector,
        recovery_service=recovery,
        quality_gate=quality_gate
    )

@pytest.mark.asyncio
async def test_orchestrator_full_flow(orchestrator, mock_bus, mock_store):
    raw_event = {"symbol": "BTC-USDT", "venue": "binance", "seq_id": 1}
    
    await orchestrator.process(raw_event)
    
    # Verify sequence: ClockSync(await) -> Arbitrator -> GapDetector(await) -> Recovery(await) -> Normalizer -> QualityGate(await) -> Store(await) -> Bus(await)
    assert mock_store.record_event.called
    assert mock_bus.publish.called
    
    # Check that it published MARKET_DATA
    published_type = mock_bus.publish.call_args_list[0].args[0]
    assert published_type == EventType.MARKET_DATA
    
@pytest.mark.asyncio
async def test_orchestrator_rejection_blocks_pipeline(orchestrator, mock_bus, mock_store):
    # Mock quality gate to reject
    orchestrator.quality_gate.validate.return_value = False
    
    raw_event = {"symbol": "BTC-USDT", "venue": "binance", "seq_id": 1}
    await orchestrator.process(raw_event)
    
    # If rejected, should NOT record_event and NOT publish MARKET_DATA
    mock_store.record_event.assert_not_called()
    
    # Should publish DATA_REJECTED via the _run_quality_checks internally
    # Wait, in our implementation, _run_quality_checks publishes DATA_REJECTED
    assert mock_bus.publish.called
    published_type = mock_bus.publish.call_args_list[0].args[0]
    assert published_type == EventType.DATA_REJECTED
