import logging
from datetime import datetime
from typing import Any

import httpx
import polars as pl
from pydantic import BaseModel

from qtrader.core.config import Config

_LOG = logging.getLogger("qtrader.market.coinbase")


class CoinbaseMarketDataClient:
    """
    Public REST client for Coinbase Advanced Trade Market Data.
    No authentication required for these endpoints.
    """

    def __init__(self, rest_base: str | None = None) -> None:
        self.rest_base = rest_base or Config.COINBASE_REST_BASE
        self.key_name = Config.COINBASE_KEY_NAME
        self.private_key_pem = Config.COINBASE_PRIVATE_KEY.replace("\\n", "\n")
        self.timeout = 10.0

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        from qtrader.output.execution.brokers.coinbase_jwt import build_rest_jwt
        from urllib.parse import urlparse
        
        parsed = urlparse(self.rest_base)
        full_path = f"{parsed.path.rstrip('/')}{path}"

        token = build_rest_jwt(
            rest_base=self.rest_base,
            method=method,
            path=full_path,
            key_name=self.key_name,
            private_key_pem=self.private_key_pem,
        )
        return {"Authorization": f"Bearer {token}"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.rest_base}{path}"
        headers = self._auth_headers("GET", path)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            _LOG.error(f"Coinbase GET {path} failed: {e}")
            raise

    def get_candles(
        self,
        product_id: str,
        granularity: str,
        start: str | int | datetime | None = None,
        end: str | int | datetime | None = None,
    ) -> pl.DataFrame:
        """
        Fetch OHLCV candles for a product with pagination.
        Coinbase returns max 300 candles per request.
        """
        import time
        
        start_ts = int(start.timestamp()) if isinstance(start, datetime) else int(start or 0)
        end_ts = int(end.timestamp()) if isinstance(end, datetime) else int(end or time.time())
        
        all_candles: list[dict] = []
        current_end = end_ts
        
        path = f"/brokerage/products/{product_id}/candles"
        
        while current_end > start_ts:
            params = {
                "granularity": granularity,
                "start": str(start_ts),
                "end": str(current_end)
            }
            try:
                data = self._get(path, params)
                batch = data.get("candles", [])
                if not batch:
                    break
                
                all_candles.extend(batch)
                
                # Find the earliest candle in this batch to move current_end back
                earliest_in_batch = min(int(c["start"]) for c in batch)
                if earliest_in_batch >= current_end:
                    # Guard against infinite loops if API returns the same data
                    break
                    
                current_end = earliest_in_batch - 1
                
                # Respect rate limits (public API is approx 10 req/sec)
                # We'll just do a tiny sleep if it's a large request
                if len(all_candles) > 1000:
                    time.sleep(0.1)
                
                # If we got fewer than 300, we've likely hit the start
                if len(batch) < 300:
                    break
                    
            except Exception as e:
                _LOG.error(f"Error fetching candle batch: {e}")
                break

        if not all_candles:
            return pl.DataFrame()

        df = pl.DataFrame(all_candles)
        df = df.with_columns([
            pl.from_epoch(pl.col("start").cast(pl.Int64), time_unit="s").alias("timestamp"),
            pl.col("open").cast(pl.Float64),
            pl.col("high").cast(pl.Float64),
            pl.col("low").cast(pl.Float64),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
        ]).select(["timestamp", "open", "high", "low", "close", "volume"])
        
        return df.sort("timestamp").unique(subset=["timestamp"])

    def get_product_book(self, product_id: str, limit: int = 10) -> dict[str, Any]:
        """
        Fetch L2 order book depth for a product.
        """
        path = "/brokerage/product_book"
        params = {"product_id": product_id, "limit": limit}
        data = self._get(path, params)
        
        # Format: {"pricebook": {"product_id": "BTC-USD", "bids": [...], "asks": [...], "time": "..."}}
        pb = data.get("pricebook", {})
        
        return {
            "bids": [{"price": float(b["price"]), "size": float(b.get("size", b.get("volume", 0)))} for b in pb.get("bids", [])],
            "asks": [{"price": float(a["price"]), "size": float(a.get("size", a.get("volume", 0)))} for a in pb.get("asks", [])]
        }

    def get_best_bid_ask(self, product_ids: list[str]) -> dict[str, dict[str, float]]:
        """
        Fetch the best bid and ask for multiple products.
        Returns: { "BTC-USD": {"bid": 60000.0, "ask": 60001.0, "bid_size": 1.0, "ask_size": 1.0} }
        """
        path = "/brokerage/best_bid_ask"
        params = {"product_ids": product_ids}
        # Note: product_ids is passed as a repeated query param: ?product_ids=BTC-USD&product_ids=ETH-USD
        # httpx handles list params automatically
        data = self._get(path, params)
        
        pricebooks = data.get("pricebooks", [])
        result = {}
        for pb in pricebooks:
            pid = pb.get("product_id")
            bids = pb.get("bids", [])
            asks = pb.get("asks", [])
            
            best_bid = float(bids[0]["price"]) if bids else 0.0
            best_ask = float(asks[0]["price"]) if asks else 0.0
            bid_size = float(bids[0].get("size", bids[0].get("volume", 0))) if bids else 0.0
            ask_size = float(asks[0].get("size", asks[0].get("volume", 0))) if asks else 0.0
            
            result[pid] = {
                "bid": best_bid,
                "ask": best_ask,
                "bid_size": bid_size,
                "ask_size": ask_size
            }
        return result
