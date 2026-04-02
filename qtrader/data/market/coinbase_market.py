import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
import polars as pl
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from qtrader.core.config import Config
from qtrader.core.decimal_adapter import math_authority

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
        from urllib.parse import urlparse

        from qtrader.execution.brokers.coinbase_jwt import build_rest_jwt
        
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

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.RequestError)),
        before_sleep=before_sleep_log(_LOG, logging.WARNING),
        reraise=True
    )
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.rest_base}{path}"
        headers = self._auth_headers("GET", path)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 429 or resp.status_code >= 500:
                resp.raise_for_status()
            elif resp.status_code != 200:
                resp.raise_for_status()
            
            return resp.json()

    async def get_candles(
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
        from datetime import datetime

        from qtrader.core.config import Config
        
        start_ts = int(start.timestamp()) if isinstance(start, datetime) else int(start or 0)
        end_ts = int(end.timestamp()) if isinstance(end, datetime) else int(end or datetime.now(Config.tz).timestamp())
        
        # Granularity mapping to seconds to calculate chunk sizes
        G_MAP = {
            "ONE_SECOND": 1,
            "ONE_MINUTE": 60,
            "FIVE_MINUTE": 300,
            "FIFTEEN_MINUTE": 900,
            "THIRTY_MINUTE": 1800,
            "ONE_HOUR": 3600,
            "SIX_HOUR": 21600,
            "ONE_DAY": 86400,
        }
        step_secs = G_MAP.get(granularity, 3600) * 300
        
        all_candles: list[dict] = []
        current_end = end_ts
        
        path = f"/brokerage/products/{product_id}/candles"
        
        while current_end > start_ts:
            # We request from current_end back to (current_end - 300 intervals)
            chunk_start = max(start_ts, current_end - step_secs)
            
            params = {
                "granularity": granularity,
                "start": str(chunk_start),
                "end": str(current_end)
            }
            try:
                data = await self._get(path, params)
                batch = data.get("candles", [])
                if not batch:
                    if current_end > chunk_start:
                        current_end = chunk_start
                    else:
                        break
                    continue
                
                all_candles.extend(batch)
                
                earliest_in_batch = min(int(c["start"]) for c in batch)
                
                if earliest_in_batch < current_end:
                    current_end = earliest_in_batch
                else:
                    current_end = chunk_start
                
                if current_end <= start_ts:
                    break
                    
                await asyncio.sleep(0.15)
                
            except Exception as e:
                _LOG.error(f"Error fetching candle batch at {current_end}: {e}")
                await asyncio.sleep(1.0)
                break

        if not all_candles:
            return pl.DataFrame()

        df = pl.DataFrame(all_candles)
        df = df.with_columns([
            pl.from_epoch(pl.col("start").cast(pl.Int64), time_unit="s")
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone(Config.TIMEZONE)
            .alias("timestamp"),
            pl.col("open").cast(pl.String).map_elements(lambda x: math_authority.d(x), return_dtype=pl.Object).alias("open"),
            pl.col("high").cast(pl.String).map_elements(lambda x: math_authority.d(x), return_dtype=pl.Object).alias("high"),
            pl.col("low").cast(pl.String).map_elements(lambda x: math_authority.d(x), return_dtype=pl.Object).alias("low"),
            pl.col("close").cast(pl.String).map_elements(lambda x: math_authority.d(x), return_dtype=pl.Object).alias("close"),
            pl.col("volume").cast(pl.String).map_elements(lambda x: math_authority.d(x), return_dtype=pl.Object).alias("volume"),
        ]).select(["timestamp", "open", "high", "low", "close", "volume"])
        
        return df.sort("timestamp").unique(subset=["timestamp"])

    async def get_product_book(self, product_id: str, limit: int = 10) -> dict[str, Any]:
        """
        Fetch L2 order book depth for a product.
        """
        path = "/brokerage/product_book"
        params = {"product_id": product_id, "limit": limit}
        data = await self._get(path, params)
        
        pb = data.get("pricebook", {})
        
        return {
            "bids": [{"price": math_authority.d(b["price"]), "size": math_authority.d(b.get("size", b.get("volume", 0)))} for b in pb.get("bids", [])],
            "asks": [{"price": math_authority.d(a["price"]), "size": math_authority.d(a.get("size", a.get("volume", 0)))} for a in pb.get("asks", [])]
        }

    async def get_best_bid_ask(self, product_ids: list[str]) -> dict[str, dict[str, Decimal]]:
        """
        Fetch the best bid and ask for multiple products.
        Returns: { "BTC-USD": {"bid": Decimal("60000.0"), "ask": Decimal("60001.0"), "bid_size": Decimal("1.0"), "ask_size": Decimal("1.0")} }
        """
        path = "/brokerage/best_bid_ask"
        params = {"product_ids": product_ids}
        data = await self._get(path, params)
        
        pricebooks = data.get("pricebooks", [])
        result = {}
        for pb in pricebooks:
            pid = pb.get("product_id")
            bids = pb.get("bids", [])
            asks = pb.get("asks", [])
            
            best_bid = math_authority.d(bids[0]["price"]) if bids else Decimal("0")
            best_ask = math_authority.d(asks[0]["price"]) if asks else Decimal("0")
            bid_size = math_authority.d(bids[0].get("size", bids[0].get("volume", 0))) if bids else Decimal("0")
            ask_size = math_authority.d(asks[0].get("size", asks[0].get("volume", 0))) if asks else Decimal("0")
            
            result[pid] = {
                "bid": best_bid,
                "ask": best_ask,
                "bid_size": bid_size,
                "ask_size": ask_size
            }
        return result
