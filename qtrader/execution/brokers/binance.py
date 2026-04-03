import asyncio
import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any, Callable

import aiohttp

from qtrader.core.config import Config
from qtrader.core.events import FillEvent, OrderEvent
from qtrader.execution.brokers.base import BrokerAdapter
from qtrader.execution.http import RetryConfig, request_json


class BinanceBrokerAdapter(BrokerAdapter):
    """Production Binance API adapter (Spot) with WebSocket user data stream."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        testnet: bool | None = None,
        *,
        request_timeout_s: float = 10.0,
        max_retries: int = 3,
        retry_backoff_ms: int = 200,
    ) -> None:
        self.api_key = api_key or Config.BINANCE_API_KEY
        self.api_secret = api_secret or Config.BINANCE_API_SECRET
        is_testnet = testnet if testnet is not None else Config.SIMULATE_MODE
        self.base_url = (
            "https://testnet.binance.vision" if is_testnet else "https://api.binance.com"
        )
        self.ws_url = (
            "wss://testnet.binance.vision" if is_testnet else "wss://stream.binance.com:9443"
        )
        self._log = logging.getLogger("qtrader.broker.binance")
        self._order_symbol: dict[str, str] = {}  # broker_oid -> symbol
        self._retry = RetryConfig(
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        self._session: aiohttp.ClientSession | None = None

        # WebSocket user data stream state
        self._listen_key: str | None = None
        self._ws_task: asyncio.Task | None = None
        self._ws_running = False
        self._on_order_update: Callable[[dict[str, Any]], None] | None = None
        self._on_balance_update: Callable[[dict[str, Any]], None] | None = None
        self._keep_alive_interval = 1800  # 30 minutes (Binance requirement)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _generate_signature(self, params: dict[str, Any]) -> str:
        query_string = urllib.parse.urlencode(params, doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

    async def _request(
        self, method: str, path: str, signed: bool = False, params: dict[str, Any] | None = None
    ) -> Any:
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._generate_signature(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        session = await self._get_session()
        return await request_json(
            session=session,
            method=method,
            url=f"{self.base_url}{path}",
            headers=headers,
            params=params,
            retry=self._retry,
        )

    async def submit_order(self, order: OrderEvent) -> str:
        """Submits a LIMIT or MARKET order to Binance."""
        params = {
            "symbol": order.symbol.upper(),
            "side": order.side.upper(),
            "type": order.order_type.upper(),
            "quantity": order.quantity,
        }
        if order.price:
            params["price"] = order.price
            params["timeInForce"] = "GTC"

        res = await self._request("POST", "/api/v3/order", signed=True, params=params)
        broker_oid = str(res.get("orderId", ""))
        if broker_oid:
            self._order_symbol[broker_oid] = params["symbol"]
        return broker_oid

    async def cancel_order(self, order_id: str) -> bool:
        symbol = self._order_symbol.get(order_id)
        if not symbol:
            self._log.warning(
                "Cancel requested for unknown order_id=%s (missing symbol mapping)", order_id
            )
            return False
        params = {"symbol": symbol, "orderId": order_id}
        res = await self._request("DELETE", "/api/v3/order", signed=True, params=params)
        return "orderId" in res or str(res.get("orderId", "")) == str(order_id)

    async def get_fills(self, order_id: str) -> list[FillEvent]:
        # Fetch fills via /myTrades (requires symbol).
        symbol = self._order_symbol.get(order_id)
        if not symbol:
            return []
        trades = await self._request(
            "GET",
            "/api/v3/myTrades",
            signed=True,
            params={"symbol": symbol},
        )
        fills: list[FillEvent] = []
        if not isinstance(trades, list):
            return fills
        for t in trades:
            if str(t.get("orderId")) != str(order_id):
                continue
            qty = float(t.get("qty") or 0.0)
            price = float(t.get("price") or 0.0)
            commission = float(t.get("commission") or 0.0)
            is_buyer = bool(t.get("isBuyer"))
            side = "BUY" if is_buyer else "SELL"
            trade_id = str(t.get("id") or t.get("tradeId") or "")
            fills.append(
                FillEvent(
                    symbol=symbol,
                    quantity=qty,
                    price=price,
                    commission=commission,
                    side=side,
                    order_id=order_id,
                    fill_id=trade_id or order_id,
                )
            )
        return fills

    async def get_balance(self) -> dict:
        res = await self._request("GET", "/api/v3/account", signed=True)
        balances = {b["asset"]: float(b["free"]) for b in res.get("balances", [])}
        return balances

    # ========================================================================
    # WebSocket User Data Stream
    # ========================================================================

    async def start_user_data_stream(self) -> str:
        """Start Binance User Data Stream and return listen key."""
        res = await self._request("POST", "/api/v3/userDataStream", signed=False)
        self._listen_key = res.get("listenKey")
        if not self._listen_key:
            raise RuntimeError("Failed to get listen key from Binance")
        self._log.info(f"[BINANCE_WS] User data stream started: {self._listen_key[:10]}...")
        return self._listen_key

    async def keep_alive_user_data_stream(self) -> None:
        """Keep the user data stream alive (must be called every 30 minutes)."""
        if not self._listen_key:
            return
        await self._request(
            "PUT", "/api/v3/userDataStream", signed=False, params={"listenKey": self._listen_key}
        )
        self._log.debug("[BINANCE_WS] User data stream keep-alive sent")

    def set_order_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for order update events from WebSocket."""
        self._on_order_update = handler

    def set_balance_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for balance update events from WebSocket."""
        self._on_balance_update = handler

    async def start_websocket(self) -> None:
        """Start WebSocket connection for real-time order and balance updates."""
        if self._ws_running:
            return

        if not self._listen_key:
            await self.start_user_data_stream()

        self._ws_running = True
        self._ws_task = asyncio.create_task(self._websocket_loop())
        self._log.info("[BINANCE_WS] WebSocket loop started")

    async def stop_websocket(self) -> None:
        """Stop WebSocket connection."""
        self._ws_running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._log.info("[BINANCE_WS] WebSocket loop stopped")

    async def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        while self._ws_running:
            try:
                ws_url = f"{self.ws_url}/ws/{self._listen_key}"
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(ws_url) as ws:
                        self._log.info(f"[BINANCE_WS] Connected to {ws_url}")
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_ws_message(msg.json())
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                self._log.warning(
                                    "[BINANCE_WS] Connection closed/error, reconnecting..."
                                )
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"[BINANCE_WS] Error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        event_type = data.get("e")

        if event_type == "executionReport":
            # Order update event
            if self._on_order_update:
                self._on_order_update(data)

            # Track fill events from execution reports
            if data.get("X") == "FILLED" or data.get("X") == "PARTIALLY_FILLED":
                broker_oid = str(data.get("i", ""))
                if broker_oid:
                    self._order_symbol[broker_oid] = data.get("s", "")

        elif event_type == "outboundAccountPosition":
            # Balance update event
            if self._on_balance_update:
                self._on_balance_update(data)

        elif event_type == "listenKeyExpired":
            self._log.warning("[BINANCE_WS] Listen key expired, restarting stream...")
            self._listen_key = None
            await self.start_user_data_stream()

    async def close(self) -> None:
        """Close all connections."""
        await self.stop_websocket()
        if self._listen_key:
            try:
                await self._request(
                    "DELETE",
                    "/api/v3/userDataStream",
                    signed=False,
                    params={"listenKey": self._listen_key},
                )
            except Exception:
                pass
        if self._session is not None and not self._session.closed:
            await self._session.close()
