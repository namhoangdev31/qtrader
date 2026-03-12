from typing import Dict, Any, List, Callable, Optional
from qtrader.core.event import MarketDataEvent
from qtrader.core.config import Config

class CoinbaseConnector:
    """
    Connects to Coinbase Advanced Trade WebSocket API.
    Provides real-time normalization of ticker and L2 events.
    """
    
    WS_URL = "wss://advanced-trade-websocket.coinbase.com"

    def __init__(self, product_ids: List[str], api_key: Optional[str] = None, api_secret: Optional[str] = None) -> None:
        self.product_ids = product_ids
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.is_running = False
        self.callback: Optional[Callable] = None

    async def connect(self, callback: Callable):
        """Main loop for WebSocket connection."""
        self.callback = callback
        self.is_running = True
        
        async for websocket in websockets.connect(self.WS_URL):
            try:
                # 1. Subscribe to channels
                subscribe_msg = {
                    "type": "subscribe",
                    "product_ids": self.product_ids,
                    "channel": "ticker", # ticker or l2_data
                }
                # Note: Real implementation needs signature for authenticated private channels
                # For public ticker, subscription is straightforward
                await websocket.send(json.dumps(subscribe_msg))
                
                # 2. Consume messages
                async for message in websocket:
                    data = json.loads(message)
                    event = self._normalize(data)
                    if event and self.callback:
                        await self.callback(event)
                        
            except websockets.ConnectionClosed:
                logging.warning("COINBASE | Connection closed. Reconnecting...")
                continue
            except Exception as e:
                logging.error(f"COINBASE | Error: {e}")
                break

    def _normalize(self, data: Dict[str, Any]) -> Optional[MarketDataEvent]:
        """Convert Coinbase WS message to QTrader MarketDataEvent."""
        if data.get("channel") == "ticker":
            events = data.get("events", [])
            for e in events:
                tickers = e.get("tickers", [])
                for t in tickers:
                    return MarketDataEvent(
                        symbol=t["product_id"],
                        timestamp=None, # In production, parse ISO timestamp
                        last_price=float(t["price"]),
                        volume=0.0 # Ticker might not have cumulative vol
                    )
        return None

    def stop(self):
        self.is_running = False
