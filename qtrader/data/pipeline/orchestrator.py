from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from qtrader.core.event import (
    DataErrorEvent,
    DataRejectedEvent,
    EventType,
    MarketDataEvent,
)
from qtrader.data.market.clock_sync import ClockSync
from qtrader.data.market.snapshot_recovery import RecoveryEngine
from qtrader.data.pipeline.arbitrator import Arbitrator
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.data.pipeline.recovery import RecoveryService
from qtrader.data.quality_gate import DataQualityGate

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
    from qtrader.data.pipeline.base import DataNormalizer
    from qtrader.oms.event_store import EventStore

LATENCY_THRESHOLD_MS = 50.0


class MarketPipelineOrchestrator:
    """The central deterministic orchestrator that sequences all stages of the market data pipeline.
    
    Ensures a unified, ordered flow from raw source data to validated MarketDataEvent.
    Eliminates data races and provides a single control point for error recovery.
    """

    def __init__(  # noqa: PLR0913
        self,
        event_bus: EventBus,
        event_store: EventStore,
        normalizer: DataNormalizer,
        arbitrator: Arbitrator | None = None,
        clock_sync: ClockSync | None = None,
        gap_detector: GapDetector | None = None,
        recovery_service: RecoveryService | None = None,
        quality_gate: DataQualityGate | None = None,
    ) -> None:
        """
        Initialize the MarketPipelineOrchestrator with its constituent stages.
        """
        self.event_bus = event_bus
        self.event_store = event_store
        self.normalizer = normalizer
        
        # Initialize stages with the shared store and bus
        self.clock_sync = clock_sync or ClockSync(event_store, event_bus)
        self.arbitrator = arbitrator or Arbitrator()
        self.gap_detector = gap_detector or GapDetector(event_store, event_bus)
        
        # Recovery Service requires the RecoveryEngine
        if not recovery_service:
            engine = RecoveryEngine(event_store, event_bus)
            self.recovery_service = RecoveryService(engine, event_bus)
        else:
            self.recovery_service = recovery_service
            
        self.quality_gate = quality_gate or DataQualityGate(event_bus)

    async def start(self) -> None:
        """Lifecycle start for the pipeline orchestrator."""
        logger.info("MarketPipelineOrchestrator: Starting stages...")
        await self.clock_sync.start()
        
    async def stop(self) -> None:
        """Lifecycle stop for the pipeline orchestrator."""
        logger.info("MarketPipelineOrchestrator: Stopping stages...")
        await self.clock_sync.stop()

    async def process(self, raw_data: dict[str, Any]) -> MarketDataEvent | None:
        """Route raw exchange data through the full sequential pipeline.
        
        Order:
        1. Clock Sync (Normalize timestamps)
        2. Feed Arbitration (Best source selection)
        3. Gap Detection (Sequence continuity check)
        4. Recovery (Snapshot reconstruction)
        5. Normalization (To canonical format)
        6. Quality Gate (Statistical/Cross-exchange verification)
        7. Audit Log (Record validated event)
        8. Emit (Publish to EventBus)
        """
        try:
            # Stage 1: Clock Sync & Timestamp Normalization
            synced_data = await self.clock_sync.handle(raw_data)
            
            # Stage 2: Feed Arbitration (A/B Feed selection)
            selected_data = self.arbitrator.handle(synced_data)
            if not selected_data:
                return None
                
            # Stage 3: Gap Detection
            gapped_data = await self.gap_detector.handle(selected_data)
            
            # Stage 4: Recovery (Triggered only if metadata["gap_detected"] is True)
            recovered = await self.recovery_service.handle(gapped_data)
            if not recovered:
                return None
                
            # Stage 5: Normalization
            event = self.normalizer.normalize(recovered)
            if not event:
                return None
                
            # Stage 6: Data Quality Gate (MAD Filter + Cross-Exchange Sanity)
            is_valid = await self._run_quality_checks(event)
            if not is_valid:
                return None
            
            # Stage 7: Audit Log (Record Validated Event)
            await self.event_store.record_event(event)
            
            # Stage 8: System Emit
            await self.event_bus.publish(EventType.MARKET_DATA, event)
            
            return event

        except Exception as e:
            logger.exception(f"Orchestrator: Critical pipeline failure: {e}")
            error_ev = DataErrorEvent(
                symbol=raw_data.get("symbol", "unknown"),
                reason=str(e),
                trace_id=raw_data.get("trace_id", "pending")
            )
            await self.event_bus.publish(EventType.DATA_ERROR, error_ev)
            return None

    async def _run_quality_checks(self, event: MarketDataEvent) -> bool:
        """Run statistical MAD and cross-exchange consistency checks."""
        symbol = event.symbol
        venue = event.metadata.get("venue") if event.metadata else "unknown"
        
        rolling_prices = self.event_store.get_recent_prices(symbol, window_size=50)
        
        # Ensure venue is a string for Mypy
        venue_str = str(venue) if venue else "unknown"
        ref_price = self.event_store.get_latest_price_cross_exchange(
            symbol, exclude_venue=venue_str
        )
        
        is_valid = self.quality_gate.validate(
            event, 
            rolling_prices, 
            ref_price=ref_price,
            z_threshold=3.0,
            epsilon_pct=0.01
        )
        
        if not is_valid:
            rejected_ev = DataRejectedEvent(
                symbol=symbol,
                trace_id=event.trace_id,
                reason="Outlier/Cross-exchange deviation",
                value=event.close,
                threshold=3.0,
            )
            await self.event_bus.publish(EventType.DATA_REJECTED, rejected_ev)
            
        return is_valid
