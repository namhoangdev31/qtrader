import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import websockets

from qtrader.core.config import Config
from qtrader.core.event import MarketDataEvent


class CoinbaseConnector:
    """
    Connects to Coinbase Advanced Trade WebSocket API and emits MarketDataEvent.

    Notes:
    - This is a minimal public-channel connector meant to feed OMS market_state/SOR.
    - Events are normalized into `MarketDataEvent(symbol=..., data={...})` with `venue="coinbase"`.
    """

    WS_URL = "wss://advanced-trade-websocket.coinbase.com"

    def __init__(
        self,
        product_ids: list[str],
        api_key: str | None = None,
        api_secret: str | None = None,
        channel: str = "ticker",
    ) -> None:
        self.product_ids = product_ids
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.channel = channel
        self.is_running = False
        self.callback: Callable[[MarketDataEvent], Any] | None = None
        self._log = logging.getLogger("qtrader.input.data.coinbase_ws")

    async def connect(self, callback: Callable[[MarketDataEvent], Any]) -> None:
        self.callback = callback
        self.is_running = True

        while self.is_running:
            try:
                async with websockets.connect(self.WS_URL) as websocket:
                    subscribe_msg = {
                        "type": "subscribe",
                        "product_ids": self.product_ids,
                        "channel": self.channel,  # e.g. "ticker"
                    }
                    await websocket.send(json.dumps(subscribe_msg))

                    async for message in websocket:
                        data = json.loads(message)
                        event = self._normalize(data)
                        if event is not None and self.callback is not None:
                            await self.callback(event)
            except websockets.ConnectionClosed:
                self._log.warning("Connection closed. Reconnecting...")
                await asyncio.sleep(1.0)
                continue
            except Exception as e:
                self._log.error("Coinbase WS error: %s", e)
                await asyncio.sleep(1.0)

    def _normalize(self, data: dict[str, Any]) -> MarketDataEvent | None:
        # Coinbase Advanced Trade WS envelopes contain channel + events list.
        channel = data.get("channel")
        if channel != "ticker":
            return None

        events = data.get("events", [])
        for e in events:
            tickers = e.get("tickers", [])
            for t in tickers:
                symbol = t.get("product_id")
                if not symbol:
                    continue
                # Prefer best bid/ask if present; fall back to last trade price.
                price = float(t.get("price") or 0.0)
                bid = float(t.get("best_bid") or price or 0.0)
                ask = float(t.get("best_ask") or price or 0.0)

                return MarketDataEvent(
                    symbol=symbol,
                    data={
                        "venue": "coinbase",
                        "last_price": price,
                        "bid": bid,
                        "ask": ask,
                        "bid_size": float(t.get("best_bid_size") or 0.0),
                        "ask_size": float(t.get("best_ask_size") or 0.0),
                    },
                )
        return None

    def stop(self) -> None:
        self.is_running = False

