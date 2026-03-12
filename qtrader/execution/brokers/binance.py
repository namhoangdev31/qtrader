from typing import List, Dict, Any, Optional
from qtrader.core.event import OrderEvent, FillEvent
from qtrader.execution.brokers.base import BrokerAdapter
from qtrader.core.config import Config

class BinanceBrokerAdapter(BrokerAdapter):
    """Production Binance API adapter (Spot)."""
    
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None, testnet: Optional[bool] = None) -> None:
        self.api_key = api_key or Config.BINANCE_API_KEY
        self.api_secret = api_secret or Config.BINANCE_API_SECRET
        is_testnet = testnet if testnet is not None else Config.SIMULATE_MODE
        self.base_url = "https://testnet.binance.vision" if is_testnet else "https://api.binance.com"

    def _generate_signature(self, params: Dict[str, Any]) -> str:
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    async def _request(self, method: str, path: str, signed: bool = False, params: Optional[Dict[str, Any]] = None) -> Any:
        params = params or {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._generate_signature(params)

        headers = {"X-MBX-APIKEY": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.request(method, f"{self.base_url}{path}", params=params, headers=headers) as resp:
                return await resp.json()

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
        return str(res.get("orderId", ""))

    async def cancel_order(self, order_id: str, symbol: str) -> bool: # Added symbol for Binance
        params = {"symbol": symbol.upper(), "orderId": order_id}
        res = await self._request("DELETE", "/api/v3/order", signed=True, params=params)
        return "orderId" in res

    async def get_fills(self, order_id: str, symbol: str) -> List[FillEvent]:
        # Binance fills are usually available via the account info or order status
        # This is a simplified version
        res = await self._request("GET", "/api/v3/order", signed=True, params={
            "symbol": symbol.upper(), 
            "orderId": order_id
        })
        # Logic to convert Binance response to FillEvent
        return []

    async def get_balance(self) -> dict:
        res = await self._request("GET", "/api/v3/account", signed=True)
        balances = {b["asset"]: float(b["free"]) for b in res.get("balances", [])}
        return balances
