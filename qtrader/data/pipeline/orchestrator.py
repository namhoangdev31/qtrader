from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

from loguru import logger

from qtrader.core.event import (
    DataErrorEvent,
    EventType,
    GapFreeMarketEvent,
    MarketDataEvent,
    RecoveryCompletedEvent,
    DataRejectedEvent,
)
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.arbitrator import Arbitrator
from qtrader.data.pipeline.base import DataNormalizer
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.data.pipeline.recovery import RecoveryService
from qtrader.data.market.clock_sync import ClockSync
from qtrader.data.market.snapshot_recovery import RecoveryEngine
from qtrader.data.quality_gate import DataQualityError, DataQualityGate

if TYPE_CHECKING:
    from qtrader.oms.event_store import EventStore

LATENCY_THRESHOLD_MS = 50.0


class MarketPipelineOrchestrator:
    """The central deterministic orchestrator that sequences all stages of the market data pipeline.
    
    Ensures a unified, ordered flow from raw source data to validated MarketDataEvent.
    Eliminates data races and provides a single control point for error recovery.
    """

    def __init__(
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
        if recovery_service:
            self.recovery_service = recovery_service
        else:
            engine = RecoveryEngine(event_store, event_bus)
            self.recovery_service = RecoveryService(engine, event_bus)
            
        self.quality_gate = quality_gate or DataQualityGate(event_bus)

    async def start(self) -> None:
        """Start the pipeline and its internal stages."""
        await self.clock_sync.start()
        logger.info("MarketPipeline: Started all stages.")

    async def stop(self) -> None:
        """Stop the pipeline and its internal stages."""
        await self.clock_sync.stop()
        logger.info("MarketPipeline: Stopped all stages.")

    async def process(self, raw_event: dict[str, Any]) -> None:
        """Sequential processing of a raw market feed event.
        
        Args:
            raw_event: The dictionary from the raw market source (e.g. WebSocket).
        """
        start_time = time.perf_counter()
        trace_id = raw_event.get("trace_id", "pending")
        symbol = raw_event.get("symbol", "unknown")
        
        metrics: dict[str, float] = {}

        try:
            # Stage 1: Clock Synchronization (Normalize timestamps)
            s_clock_start = time.perf_counter()
            event = await self.clock_sync.handle(raw_event)
            metrics["clock_sync_ms"] = (time.perf_counter() - s_clock_start) * 1000

            # Stage 2: Feed Arbitration (A/B Feed selection)
            s1_start = time.perf_counter()
            event = self.arbitrator.handle(event)
            metrics["arbitration_ms"] = (time.perf_counter() - s1_start) * 1000
            if event is None:
                return  # Arbitration dropped the event (duplicate/inferior)

            # Stage 3: Gap Detection
            s2_start = time.perf_counter()
            event = await self.gap_detector.handle(event)
            metrics["gap_detection_ms"] = (time.perf_counter() - s2_start) * 1000

            # Stage 4: Recovery (if gap detected)
            s3_start = time.perf_counter()
            event = await self.recovery_service.handle(event)
            metrics["recovery_ms"] = (time.perf_counter() - s3_start) * 1000
            if event is None:
                return  # Recovery failed or dropped
            
            # Stage 5: Normalization (if not recovered)
            s4_start = time.perf_counter()
            if event.get("metadata", {}).get("gap_free_event"):
                # Use reconstructed event directly
                market_event = event["metadata"]["gap_free_event"]
            else:
                market_event = self.normalizer.normalize(event)
            metrics["normalization_ms"] = (time.perf_counter() - s4_start) * 1000
            
            # Stage 6: Data Quality Gate (Statistical MAD + Cross-Exchange)
            s6_start = time.perf_counter()
            is_valid = await self._run_quality_checks(market_event)
            metrics["quality_gate_ms"] = (time.perf_counter() - s6_start) * 1000
            
            if not is_valid:
                return # Block invalid data from entering the system
            
            # Stage 7: Persistent Logging (Stateless Anchor)
            await self.event_store.record_event(market_event)

            # Total Latency Calculation
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            
            # Publish to EventBus
            if isinstance(market_event, GapFreeMarketEvent):
                publish_type = EventType.GAP_FREE_MARKET
            else:
                publish_type = EventType.MARKET_DATA

            await self.event_bus.publish(publish_type, market_event)
            
            # Monitoring
            if total_duration_ms > LATENCY_THRESHOLD_MS:
                logger.warning(
                    "Pipeline High Latency Alert: {:.2f}ms for {} - trace={}",
                    total_duration_ms, symbol, trace_id
                )
            logger.debug(
                "MarketPipeline: Processed {} in {:.2f}ms. Trace: {}",
                symbol, total_duration_ms, trace_id
            )

        except DataQualityError as exc:
            logger.error(f"Pipeline: Quality check failed for {symbol}: {exc}. Breaking pipeline.")
            await self._emit_error("quality_gate", str(exc), symbol, trace_id)
            
        except Exception as exc:
            logger.exception(f"Pipeline: Unknown failure during processing for {symbol}: {exc}")
            await self._emit_error("orchestrator", str(exc), symbol, trace_id)

    async def _run_quality_checks(self, event: MarketDataEvent) -> bool:
        """Run statistical MAD and cross-exchange consistency checks.
        
        Fetches necessary state (rolling window, ref price) from EventStore
        to maintain stateless pipeline execution.
        """
        import uuid
        symbol = event.symbol
        venue = event.metadata.get("venue") if event.metadata else "unknown"
        
        # 1. Fetch stateless context from EventStore
        recent_prices = self.event_store.get_recent_prices(symbol, window_size=50)
        ref_price = self.event_store.get_latest_price_cross_exchange(symbol, exclude_venue=venue)
        
        # 2. Synchronous validation logic
        is_valid = self.quality_gate.validate(
            event=event,
            recent_prices=recent_prices,
            ref_price=ref_price,
            z_threshold=3.0,
            epsilon_pct=0.05
        )
        
        if not is_valid:
            # Emit DataRejectedEvent (already logged by gate)
            rejected_ev = DataRejectedEvent(
                event_id=str(uuid.uuid4()),
                symbol=symbol,
                trace_id=event.trace_id,
                reason="MAD Outlier or Cross-Exchange Deviation",
                value=event.close,
                threshold=3.0,
            )
            await self.event_bus.publish(EventType.DATA_REJECTED, rejected_ev)
            return False
            
        return True

    async def _emit_error(self, stage: str, message: str, symbol: str, trace_id: str) -> None:
        """Emit a DataErrorEvent describing a pipeline failure."""
        error_event = DataErrorEvent(
            type=EventType.DATA_ERROR,
            source=stage,
            message=message,
            symbol=symbol,
            trace_id=trace_id,
            severity="ERROR",
        )
        await self.event_bus.publish(EventType.DATA_ERROR, error_event)
