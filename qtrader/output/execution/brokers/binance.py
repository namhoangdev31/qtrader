import hashlib
import hmac
import logging
import time
import urllib.parse
from typing import Any

import aiohttp

from qtrader.core.config import Config
from qtrader.core.event import FillEvent, OrderEvent
from qtrader.output.execution.brokers.base import BrokerAdapter
from qtrader.output.execution.http import RetryConfig, request_json


class BinanceBrokerAdapter(BrokerAdapter):
    """Production Binance API adapter (Spot)."""
    
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
        self.base_url = "https://testnet.binance.vision" if is_testnet else "https://api.binance.com"
        self._log = logging.getLogger("qtrader.broker.binance")
        self._order_symbol: dict[str, str] = {}  # broker_oid -> symbol (needed for cancel/fills endpoints)
        self._retry = RetryConfig(
            request_timeout_s=request_timeout_s,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _generate_signature(self, params: dict[str, Any]) -> str:
        query_string = urllib.parse.urlencode(params, doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def _request(self, method: str, path: str, signed: bool = False, params: dict[str, Any] | None = None) -> Any:
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
            self._log.warning("Cancel requested for unknown order_id=%s (missing symbol mapping)", order_id)
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

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
