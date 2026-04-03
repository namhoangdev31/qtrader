import asyncio
import json
import logging
import uuid
from decimal import Decimal
from typing import Any, Callable

import aiohttp

from qtrader.core.config import Config
from qtrader.core.decimal_adapter import d
from qtrader.core.events import FillEvent, OrderEvent
from qtrader.execution.brokers.coinbase_jwt import build_rest_jwt
from qtrader.execution.http import RetryConfig, request_json


class CoinbaseBrokerAdapter:
    """
    Broker adapter for Coinbase Advanced Trade REST API.
    Supports live execution and simulation mode.

    v4 note:
    - This module provides the methods required by `BrokerAdapter` Protocol:
      `submit_order`, `cancel_order`, `get_fills`, `get_balance`.
    - Live mode REST wiring is intentionally minimal/placeholder.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        simulate: bool | None = None,
        *,
        rest_base: str | None = None,
        key_name: str | None = None,
        private_key_pem: str | None = None,
        request_timeout_s: float = 10.0,
        max_retries: int = 3,
        retry_backoff_ms: int = 200,
    ) -> None:
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.simulate = simulate if simulate is not None else Config.SIMULATE_MODE
        self._log = logging.getLogger("qtrader.broker.coinbase")
        self._rest_base = rest_base or Config.COINBASE_REST_BASE
        self._key_name = key_name or Config.COINBASE_KEY_NAME
        self._private_key_pem = private_key_pem or Config.COINBASE_PRIVATE_KEY
        self._retry = RetryConfig(
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        self._session: aiohttp.ClientSession | None = None

        # Simulation state
        self._positions: dict[str, Decimal] = {}
        self._orders: dict[str, OrderEvent] = {}
        self._fills: dict[str, list[FillEvent]] = {}
        self._quotes: dict[str, dict[str, Decimal]] = {}  # symbol -> {"bid": .., "ask": ..}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _auth_headers(self, *, method: str, path: str) -> dict[str, str]:
        if not self._key_name or not self._private_key_pem:
            raise PermissionError(
                "Missing COINBASE_KEY_NAME / COINBASE_PRIVATE_KEY for live REST mode"
            )

        from urllib.parse import urlparse

        parsed = urlparse(self._rest_base)
        full_path = f"{parsed.path.rstrip('/')}{path}"

        # fix literal \n
        raw_key = self._private_key_pem.replace("\\n", "\n")

        token = build_rest_jwt(
            rest_base=self._rest_base,
            method=method,
            path=full_path,
            key_name=self._key_name,
            private_key_pem=raw_key,
        )
        return {"Authorization": f"Bearer {token}"}

    def update_quote(self, symbol: str, bid: Decimal, ask: Decimal) -> None:
        """Optional helper to improve simulated fill pricing for MARKET orders."""
        self._quotes[symbol] = {"bid": bid, "ask": ask}

    async def submit_order(self, order: OrderEvent) -> str:
        """Submit order and return broker order id (simulation/live)."""
        broker_oid = str(uuid.uuid4())
        self._orders[broker_oid] = order
        self._log.info(
            "Placing %s %s for %s (simulate=%s)",
            order.order_type,
            order.side,
            order.symbol,
            self.simulate,
        )

        if self.simulate:
            # Simulated network latency removed for zero latency
            fill = self._simulate_fill(order=order, broker_order_id=broker_oid)
            self._fills.setdefault(broker_oid, []).append(fill)
            self._apply_simulated_position(fill)
            return broker_oid

        # Live mode: Coinbase Advanced Trade REST (JWT).
        path = "/brokerage/orders"
        url = f"{self._rest_base}{path}"

        client_order_id = order.order_id or broker_oid
        side = order.side.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"Unsupported side: {order.side}")

        order_type = order.order_type.upper()
        base_size = str(order.quantity)
        if order_type == "MARKET":
            order_config = {"market_market_ioc": {"base_size": base_size}}
        elif order_type == "LIMIT":
            if order.price is None:
                raise ValueError("LIMIT order requires price")
            order_config = {
                "limit_limit_gtc": {
                    "base_size": base_size,
                    "limit_price": str(order.price),
                }
            }
        else:
            raise ValueError(f"Unsupported order_type: {order.order_type}")

        body = {
            "client_order_id": client_order_id,
            "product_id": order.symbol,
            "side": side,
            "order_configuration": order_config,
        }

        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="POST",
            url=url,
            headers=self._auth_headers(method="POST", path=path),
            json_body=body,
            retry=self._retry,
        )

        # Typical response shape:
        # { "success": true, "success_response": { "order_id": "..." }, ... }
        if isinstance(resp, dict) and resp.get("success") is True:
            success = resp.get("success_response") or {}
            order_id = success.get("order_id") or success.get("orderId") or ""
            if order_id:
                self._orders[order_id] = order
                return str(order_id)
        raise RuntimeError(f"Coinbase order submit failed: {resp}")

    async def cancel_order(self, order_id: str) -> bool:
        self._log.info("Canceling order %s (simulate=%s)", order_id, self.simulate)
        if self.simulate:
            self._orders.pop(order_id, None)
            return True
        path = "/brokerage/orders/batch_cancel"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="POST",
            url=url,
            headers=self._auth_headers(method="POST", path=path),
            json_body={"order_ids": [order_id]},
            retry=self._retry,
        )

        # Typical response:
        # { "results": [ { "order_id": "...", "success": true, ... } ] }
        if isinstance(resp, dict):
            results = resp.get("results") or []
            for r in results:
                if str(r.get("order_id") or r.get("orderId") or "") == str(order_id):
                    return bool(r.get("success"))
        raise RuntimeError(f"Coinbase cancel failed: {resp}")

    async def get_fills(self, order_id: str) -> list[FillEvent]:
        if self.simulate:
            return list(self._fills.get(order_id, []))
        path = "/brokerage/orders/historical/fills"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()

        resp = await request_json(
            session=session,
            method="GET",
            url=url,
            headers=self._auth_headers(method="GET", path=path),
            params={"order_ids": [order_id]},
            retry=self._retry,
        )

        fills: list[FillEvent] = []
        if not isinstance(resp, dict):
            return fills
        for f in resp.get("fills") or []:
            if str(f.get("order_id") or "") != str(order_id):
                continue
            size = d(str(f.get("size") or "0.0"))
            price = d(str(f.get("price") or "0.0"))
            commission = d(str(f.get("commission") or "0.0"))
            side = str(f.get("side") or "").upper() or "BUY"
            trade_id = str(f.get("trade_id") or f.get("tradeId") or uuid.uuid4())
            fills.append(
                FillEvent(
                    symbol=str(f.get("product_id") or f.get("symbol") or ""),
                    quantity=size,
                    price=price,
                    commission=commission,
                    side=side,
                    order_id=order_id,
                    fill_id=trade_id,
                )
            )
        return fills

    async def get_balance(self) -> dict:
        if self.simulate:
            return dict(self._positions)
        path = "/brokerage/accounts"
        url = f"{self._rest_base}{path}"
        session = await self._get_session()
        resp = await request_json(
            session=session,
            method="GET",
            url=url,
            headers=self._auth_headers(method="GET", path=path),
            retry=self._retry,
        )
        balances: dict[str, Decimal] = {}
        if isinstance(resp, dict):
            for acct in resp.get("accounts") or []:
                currency = str(acct.get("currency") or "")
                avail = acct.get("available_balance") or {}
                value = d(str(avail.get("value") or "0.0"))
                if currency:
                    balances[currency] = value
        return balances

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()

    def _simulate_fill(self, order: OrderEvent, broker_order_id: str) -> FillEvent:
        quote = self._quotes.get(order.symbol, {})
        bid = quote.get("bid", d(0))
        ask = quote.get("ask", d(0))

        price = d(0)
        if order.order_type.upper() == "MARKET":
            if order.side.upper() == "BUY":
                price = ask or order.price or d(0)
            else:
                price = bid or order.price or d(0)
        elif order.price is not None:
            price = order.price
        elif bid > 0 and ask > 0:
            price = (bid + ask) / d(2)
        else:
            price = d(0)

        commission = price * order.quantity * d("0.001") if price > 0 else d(0)
        return FillEvent(
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            commission=commission,
            side=order.side,
            order_id=order.order_id or broker_order_id,
            fill_id=str(uuid.uuid4()),
        )

    def _apply_simulated_position(self, fill: FillEvent) -> None:
        asset = fill.symbol.split("-")[0]
        current = self._positions.get(asset, d(0))
        if fill.side.upper() == "BUY":
            self._positions[asset] = current + fill.quantity
        else:
            self._positions[asset] = current - fill.quantity

    # ========================================================================
    # WebSocket User Data Stream (Coinbase Advanced Trade)
    # ========================================================================

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        simulate: bool | None = None,
        *,
        rest_base: str | None = None,
        key_name: str | None = None,
        private_key_pem: str | None = None,
        request_timeout_s: float = 10.0,
        max_retries: int = 3,
        retry_backoff_ms: int = 200,
    ) -> None:
        self.api_key = api_key or Config.COINBASE_API_KEY
        self.api_secret = api_secret or Config.COINBASE_API_SECRET
        self.simulate = simulate if simulate is not None else Config.SIMULATE_MODE
        self._log = logging.getLogger("qtrader.broker.coinbase")
        self._rest_base = rest_base or Config.COINBASE_REST_BASE
        self._key_name = key_name or Config.COINBASE_KEY_NAME
        self._private_key_pem = private_key_pem or Config.COINBASE_PRIVATE_KEY
        self._retry = RetryConfig(
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        self._session: aiohttp.ClientSession | None = None

        # Simulation state
        self._positions: dict[str, Decimal] = {}
        self._orders: dict[str, OrderEvent] = {}
        self._fills: dict[str, list[FillEvent]] = {}
        self._quotes: dict[str, dict[str, Decimal]] = {}  # symbol -> {"bid": .., "ask": ..}

        # WebSocket user data stream state
        self._ws_task: asyncio.Task | None = None
        self._ws_running = False
        self._ws_channels: list[str] = ["user", "heartbeat"]
        self._ws_product_ids: list[str] = []
        self._on_order_update: Callable[[dict[str, Any]], None] | None = None
        self._on_balance_update: Callable[[dict[str, Any]], None] | None = None
        self._ws_base_url = "wss://advanced-trade-ws.coinbase.com"

    def set_order_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for order update events from WebSocket."""
        self._on_order_update = handler

    def set_balance_update_handler(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Set callback for balance update events from WebSocket."""
        self._on_balance_update = handler

    def add_product(self, product_id: str) -> None:
        """Add a product (e.g., 'BTC-USD') to subscribe to."""
        if product_id not in self._ws_product_ids:
            self._ws_product_ids.append(product_id)

    async def start_websocket(self) -> None:
        """Start WebSocket connection for real-time order and balance updates."""
        if self._ws_running:
            return
        self._ws_running = True
        self._ws_task = asyncio.create_task(self._websocket_loop())
        self._log.info("[COINBASE_WS] WebSocket loop started")

    async def stop_websocket(self) -> None:
        """Stop WebSocket connection."""
        self._ws_running = False
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._log.info("[COINBASE_WS] WebSocket loop stopped")

    async def _websocket_loop(self) -> None:
        """Main WebSocket loop with auto-reconnect."""
        while self._ws_running:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(self._ws_base_url) as ws:
                        self._log.info(f"[COINBASE_WS] Connected to {self._ws_base_url}")
                        # Subscribe to channels
                        subscribe_msg = {
                            "type": "subscribe",
                            "product_ids": self._ws_product_ids,
                            "channel": self._ws_channels,
                        }
                        await ws.send_json(subscribe_msg)
                        self._log.info(
                            f"[COINBASE_WS] Subscribed to {self._ws_channels} for {self._ws_product_ids}"
                        )

                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await self._handle_ws_message(json.loads(msg.data))
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                self._log.warning(
                                    "[COINBASE_WS] Connection closed/error, reconnecting..."
                                )
                                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._log.error(f"[COINBASE_WS] Error: {e}, reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Handle incoming WebSocket message."""
        channel = data.get("channel")
        events = data.get("events", [])

        for event in events:
            if channel == "user" or "order" in event.get("type", "").lower():
                # Order update event
                if self._on_order_update:
                    self._on_order_update(event)
            elif "portfolio" in event.get("type", "").lower() or "balance" in str(event).lower():
                # Balance update event
                if self._on_balance_update:
                    self._on_balance_update(event)

    async def close(self) -> None:
        """Close all connections."""
        await self.stop_websocket()
        if self._session is not None and not self._session.closed:
            await self._session.close()
