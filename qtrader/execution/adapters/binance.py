"""
Institutional Binance Execution Adapter.
Integrates Binance Spot API with QTrader's Event-Driven Engine.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse
from decimal import Decimal
from typing import Any

import aiohttp

from qtrader.core.async_adapter import async_authority
from qtrader.core.decimal_adapter import d
from qtrader.core.events import OrderEvent
from qtrader.execution.execution_engine import ExchangeAdapter

_LOG = logging.getLogger("qtrader.execution.adapters.binance")


class BinanceAdapter(ExchangeAdapter):
    """
    Principal Binance Spot Adapter.
    
    Features: 
    - HMAC SHA256 Signing
    - Decimal Precision for all financial math
    - Async/Await non-blocking IO
    - Rate-limit aware interface
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        testnet: bool = False,
        request_timeout_s: float = 10.0
    ) -> None:
        super().__init__(name="BinanceAdapter")
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.timeout = request_timeout_s
        
        self.base_url = (
            "https://testnet.binance.vision" if testnet 
            else "https://api.binance.com"
        )
        
        self._session: aiohttp.ClientSession | None = None
        self._order_symbol_map: dict[str, str] = {}  # internal_oid -> symbol

    async def _get_session(self) -> aiohttp.ClientSession:
        return await async_authority.get_session()

    def _generate_signature(self, params: dict[str, Any]) -> str:
        query_string = urllib.parse.urlencode(params, doseq=True)
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def _request(
        self, 
        method: str, 
        path: str, 
        signed: bool = False, 
        params: dict[str, Any] | None = None
    ) -> Any:
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._generate_signature(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        session = await self._get_session()
        
        url = f"{self.base_url}{path}"
        async with session.request(method, url, headers=headers, params=params) as resp:
            if resp.status != 200:
                err = await resp.text()
                _LOG.error(f"BINANCE_API_ERROR | {resp.status} | {err}")
                raise Exception(f"Binance API error: {resp.status}")
            return await resp.json()

    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """Submits a LIMIT or MARKET order to Binance."""
        try:
            payload = order.payload
            params = {
                "symbol": payload.symbol.upper().replace("-", "").replace("/", ""),
                "side": payload.side.upper(),
                "type": payload.order_type.upper(),
                "quantity": str(payload.quantity),
                "newClientOrderId": payload.order_id
            }
            
            if payload.order_type.upper() == "LIMIT":
                params["price"] = str(payload.price)
                params["timeInForce"] = "GTC"

            res = await self._request("POST", "/api/v3/order", signed=True, params=params)
            broker_oid = str(res.get("orderId", ""))
            
            if broker_oid:
                self._order_symbol_map[broker_oid] = params["symbol"]
                _LOG.info(f"BINANCE_ORDER_SUBMITTED | Symbol: {params['symbol']} | ID: {broker_oid}")
                return True, broker_oid
            
            return False, "Failed to obtain orderId from Binance"

        except Exception as e:
            _LOG.error(f"BINANCE_SEND_FAILURE | {order.payload.order_id} | {e}")
            return False, str(e)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """Cancels an existing order by its Binance order ID."""
        try:
            symbol = self._order_symbol_map.get(order_id)
            if not symbol:
                return False, f"Unknown order_id: {order_id}"

            params = {"symbol": symbol, "orderId": order_id}
            await self._request("DELETE", "/api/v3/order", signed=True, params=params)
            return True, None
        except Exception as e:
            _LOG.error(f"BINANCE_CANCEL_FAILURE | {order_id} | {e}")
            return False, str(e)

    async def get_balance(self) -> dict[str, Decimal]:
        """Fetch account balances and return as asset -> free_qty map."""
        try:
            res = await self._request("GET", "/api/v3/account", signed=True)
            return {
                b["asset"]: d(b["free"]) 
                for b in res.get("balances", [])
            }
        except Exception as e:
            _LOG.error(f"BINANCE_BALANCE_FAILURE | {e}")
            return {}

    async def get_orderbook(self, symbol: str, limit: int = 10) -> dict[str, Any]:
        """Fetch L2 orderbook snapshot."""
        try:
            clean_symbol = symbol.upper().replace("-", "").replace("/", "")
            res = await self._request("GET", "/api/v3/depth", params={"symbol": clean_symbol, "limit": limit})
            return {
                "bids": [[d(p), d(q)] for p, q in res["bids"]],
                "asks": [[d(p), d(q)] for p, q in res["asks"]]
            }
        except Exception as e:
            _LOG.error(f"BINANCE_DEPTH_FAILURE | {symbol} | {e}")
            return {"bids": [], "asks": []}

    async def close(self) -> None:
        """Gracefully release HTTP resources."""
        if self._session and not self._session.closed:
            await self._session.close()
