import asyncio
import json
import aiohttp
from typing import Protocol, runtime_checkable, AsyncIterator, Any
from qtrader.core.event import MarketDataEvent

@runtime_checkable
class StreamingConnector(Protocol):
    """Protocol for real-time data streaming (WebSocket/FIX)."""
    async def connect(self) -> None: ...
    async def listen(self) -> AsyncIterator[Any]: ...
    async def close(self) -> None: ...

class BinanceWSConnector(StreamingConnector):
    """Binance WebSocket connector for real-time market data."""
    
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.lower()
        self.url = f"wss://stream.binance.com:9443/ws/{self.symbol}@ticker"
        self._session: Optional[aiohttp.ClientSession] = None
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

    async def connect(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(self.url)

    async def listen(self) -> AsyncIterator[dict]:
        if not self._ws:
            raise RuntimeError("Not connected")
        async for msg in self._ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                yield json.loads(msg.data)

    async def close(self) -> None:
        if self._ws:
            await self._ws.close()
        if self._session:
            await self._session.close()
