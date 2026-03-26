import asyncio
import logging
from typing import Any, Dict

from qtrader.core.event import EventType, MarketDataEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.sources.coinbase import CoinbaseConnector
from qtrader.data.pipeline.sources.streaming import BinanceWSConnector
from qtrader.execution.market_state import MarketStateUpdater

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
        event_bus: EventBus | None = None
    ) -> None:
        self.symbols = symbols
        self.venues = [v.lower() for v in venues]
        self.state_updater = state_updater
        self.event_bus = event_bus
        self._is_running = False
        self._tasks: list[asyncio.Task] = []
        
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
        
        for connector in self.connectors:
            if hasattr(connector, 'connect'):
                # Handle both signature styles (callback-based vs listen-based)
                if "coinbase" in str(type(connector)).lower():
                    task = asyncio.create_task(connector.connect(self._on_market_data))
                else:
                    task = asyncio.create_task(self._listen_to_connector(connector))
                self._tasks.append(task)
                
        _LOG.info(f"MarketFeedService multi-venue started for {self.symbols} on venues: {self.venues}")
        
    async def _listen_to_connector(self, connector: Any) -> None:
        """Generic listener for StreamingConnector protocol."""
        try:
            await connector.connect()
            async for data in connector.listen():
                if not self._is_running:
                    break
                # Normalize Binance data to MarketDataEvent (simulated normalization for brevity)
                event = self._normalize_binance(data)
                if event:
                    await self._on_market_data(event)
        except Exception as e:
            _LOG.error(f"Connector loop error: {e}")
            
    def _normalize_binance(self, data: dict) -> MarketDataEvent | None:
        """Normalize Binance @ticker payload into MarketDataEvent."""
        try:
            symbol = data.get("s", "")
            return MarketDataEvent(
                symbol=symbol,
                data={
                    "venue": "binance",
                    "last_price": float(data.get("c", 0.0)),
                    "bid": float(data.get("b", 0.0)),
                    "ask": float(data.get("a", 0.0)),
                    "bid_size": float(data.get("B", 0.0)),
                    "ask_size": float(data.get("A", 0.0)),
                }
            )
        except (ValueError, TypeError):
            return None

    async def stop(self) -> None:
        self._is_running = False
        for connector in self.connectors:
            if hasattr(connector, 'stop'):
                connector.stop()
            if hasattr(connector, 'close'):
                await connector.close()
                
        for task in self._tasks:
            task.cancel()
        
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        _LOG.info("MarketFeedService stopped")
        
    async def _on_market_data(self, event: MarketDataEvent) -> None:
        """Centralized event dispatcher."""
        if not self._is_running:
            return
            
        try:
            # Update internal market state
            await self.state_updater.on_market_data(event)
            
            # Publish to global event bus
            if self.event_bus:
                await self.event_bus.publish(EventType.MARKET_DATA, event)
                
        except Exception as e:
            _LOG.error(f"Market event processing failed: {e}")
