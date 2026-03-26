import asyncio
import logging
import time
from typing import Any

from qtrader.core.event import MarketDataEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.arbitrator import Arbitrator
from qtrader.data.pipeline.gap_detector import GapDetector
from qtrader.data.pipeline.normalizer import UnifiedNormalizer
from qtrader.data.pipeline.orchestrator import MarketPipelineOrchestrator
from qtrader.data.pipeline.sources.coinbase import CoinbaseConnector
from qtrader.data.pipeline.sources.streaming import BinanceWSConnector
from qtrader.data.quality_gate import DataQualityGate
from qtrader.execution.market_state import MarketStateUpdater
from qtrader.oms.event_store import EventStore

_LOG = logging.getLogger("qtrader.data.market_feed")

class MarketFeedService:
    """
    Unified Market Feed Orchestrator.
    Manages WebSocket connections to multiple venues (Coinbase, Binance) and emits MarketDataEvents.
    Replaces legacy polling with high-frequency streaming.
    """
    
    def __init__(
        self, 
        symbols: list[str], 
        venues: list[str],
        state_updater: MarketStateUpdater, 
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None
    ) -> None:
        self.symbols = symbols
        self.venues = [v.lower() for v in venues]
        self.state_updater = state_updater
        self.event_bus = event_bus
        self.event_store = event_store or EventStore()
        self._is_running = False
        self._tasks: list[asyncio.Task] = []
        
        # Initialize the Market Data Pipeline Orchestrator
        if self.event_bus:
            self.pipeline = MarketPipelineOrchestrator(
                event_bus=self.event_bus,
                event_store=self.event_store,
                normalizer=UnifiedNormalizer(),
                arbitrator=Arbitrator(primary_feed="A"),
                gap_detector=GapDetector(self.event_store, self.event_bus),
                recovery_service=None, # Will be auto-initialized by Orchestrator with RecoveryEngine
                quality_gate=DataQualityGate(),
            )
        else:
            self.pipeline = None
        
        # Initialize connectors based on venues
        self.connectors: list[Any] = []
        if "coinbase" in self.venues:
            self.connectors.append(CoinbaseConnector(product_ids=symbols))
            
        if "binance" in self.venues:
            for symbol in symbols:
                # Binance requires individual symbol streams in the minimal implementation
                self.connectors.append(BinanceWSConnector(symbol=symbol))
        
    async def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        
        if self.pipeline:
            await self.pipeline.start()
        
        for connector in self.connectors:
            if hasattr(connector, 'connect'):
                # Handle both signature styles (callback-based vs listen-based)
                if "coinbase" in str(type(connector)).lower():
                    # CoinbaseConnector expects a callback that takes a MarketDataEvent
                    # We'll provide a wrapper that sends raw data to the pipeline
                    task = asyncio.create_task(connector.connect(self._on_direct_market_data))
                else:
                    task = asyncio.create_task(self._listen_to_connector(connector))
                self._tasks.append(task)
                
        _LOG.info(f"MarketFeedService multi-venue started for {self.symbols} on venues: {self.venues}")
        
    async def _listen_to_connector(self, connector: Any) -> None:
        """Generic listener for StreamingConnector protocol."""
        venue = "binance" if "binance" in str(type(connector)).lower() else "unknown"
        try:
            await connector.connect()
            async for data in connector.listen():
                if not self._is_running:
                    break
                
                # Add venue and symbol info for the orchestrator
                raw_event = {
                    "venue": venue,
                    "symbol": getattr(connector, "symbol", "unknown").upper(),
                    "data": data,
                    "timestamp": time.time(),
                }
                
                # Pass to pipeline orchestrator for deterministic processing
                if self.pipeline:
                    await self.pipeline.process(raw_event)
                else:
                    # Fallback to direct state update if no event bus/pipeline
                    _LOG.warning("No pipeline configured, dropping data")
                    
        except Exception as e:
            _LOG.error(f"Connector loop error: {e}")
            
    async def _on_direct_market_data(self, event: MarketDataEvent) -> None:
        """Callback for legacy/callback-based connectors (e.g. Coinbase).
        
        Wraps the event back into a raw format for the unified pipeline.
        """
        if not self._is_running or not self.pipeline:
            return
            
        # Reconstruct raw format for the pipeline to maintain determinism
        raw_event = {
            "venue": "coinbase",
            "symbol": event.symbol,
            "bid": event.bid,
            "ask": event.ask,
            "trace_id": event.trace_id,
            "timestamp": event.timestamp.timestamp(),
        }
        await self.pipeline.process(raw_event)

    async def stop(self) -> None:
        self._is_running = False
        for connector in self.connectors:
            if hasattr(connector, 'stop'):
                connector.stop()
            if hasattr(connector, 'close'):
                await connector.close()
                
        for task in self._tasks:
            task.cancel()
        
        if self.pipeline:
            await self.pipeline.stop()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        _LOG.info("MarketFeedService stopped")
