import asyncio
import logging
from typing import Any

from qtrader.core.event import EventType, MarketDataEvent
from qtrader.core.event_bus import EventBus
from qtrader.data.pipeline.sources.coinbase import CoinbaseConnector
from qtrader.execution.market_state import MarketStateUpdater

_LOG = logging.getLogger("qtrader.market_feed")

class MarketFeedService:
    """
    Event-driven MarketFeedService using WebSocket connectors.
    Eliminates polling and replaces it with real-time stream subscriptions.
    """
    
    def __init__(
        self, 
        symbols: list[str], 
        state_updater: MarketStateUpdater, 
        event_bus: EventBus | None = None
    ) -> None:
        self.symbols = symbols
        self.state_updater = state_updater
        self.event_bus = event_bus
        self.connector = CoinbaseConnector(product_ids=symbols)
        self._is_running = False
        self._task: asyncio.Task[Any] | None = None
        
    async def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        # Start the WebSocket connector in a background task
        self._task = asyncio.create_task(self.connector.connect(self._on_market_data))
        _LOG.info(f"MarketFeedService started for {self.symbols} using WebSocket connector")
        
    async def stop(self) -> None:
        self._is_running = False
        self.connector.stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _LOG.info("MarketFeedService stopped")
        
    async def _on_market_data(self, event: MarketDataEvent) -> None:
        """Callback for incoming market data from the connector."""
        if not self._is_running:
            return
            
        try:
            # Update internal market state
            await self.state_updater.on_market_data(event)
            
            # Publish to global event bus if available
            if self.event_bus:
                await self.event_bus.publish(EventType.MARKET_DATA, event)
                
        except Exception as e:
            _LOG.error(f"Error processing market data event: {e}")
