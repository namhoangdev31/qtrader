import asyncio
import logging
from typing import Any

from qtrader.core.event import MarketDataEvent
from qtrader.input.data.market.coinbase_market import CoinbaseMarketDataClient
from qtrader.output.execution.market_state import MarketStateUpdater

_LOG = logging.getLogger("qtrader.market_feed")

class MarketFeedService:
    """
    Polls Coinbase Advanced Trade for top-of-book L2 quotes 
    and feeds them into the UnifiedOMS via MarketStateUpdater.
    """
    
    def __init__(self, symbols: list[str], state_updater: MarketStateUpdater, interval_sec: float = 1.0) -> None:
        self.symbols = symbols
        self.state_updater = state_updater
        self.interval_sec = interval_sec
        self.client = CoinbaseMarketDataClient()
        self._is_running = False
        self._task: asyncio.Task[Any] | None = None
        
    async def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._poll_loop())
        _LOG.info(f"MarketFeedService started for {self.symbols} at {self.interval_sec}s interval")
        
    async def stop(self) -> None:
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _LOG.info("MarketFeedService stopped")
        
    async def _poll_loop(self) -> None:
        while self._is_running:
            try:
                # Using Coinbase REST API for polling quotes.
                bba = self.client.get_best_bid_ask(self.symbols)
                for sym, quotes in bba.items():
                    event = MarketDataEvent(
                        symbol=sym,
                        data={
                            "bid": quotes["bid"],
                            "ask": quotes["ask"],
                            "bid_size": quotes["bid_size"],
                            "ask_size": quotes["ask_size"],
                            "venue": "coinbase"  # Matches adapter name
                        }
                    )
                    await self.state_updater.on_market_data(event)
            except Exception as e:
                _LOG.error(f"MarketFeed poll error: {e}")
                
            await asyncio.sleep(self.interval_sec)
