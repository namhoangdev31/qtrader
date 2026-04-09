from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import polars as pl
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="python-alpha-ml", version="0.1.0")


class FeatureRequest(BaseModel):
    symbol: str
    prices: list[float] = Field(default_factory=list)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "python-alpha-ml", "status": "ok"}


@app.post("/features")
async def compute_features(payload: FeatureRequest) -> dict[str, Any]:
    if not payload.prices:
        return {
            "symbol": payload.symbol,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "features": {},
            "signal": "HOLD",
            "strength": 0.0,
        }

    frame = pl.DataFrame({"close": payload.prices})
    last = float(frame.select(pl.col("close").last()).item())
    sma_5 = float(frame.select(pl.col("close").tail(5).mean()).item())
    sma_20 = float(frame.select(pl.col("close").tail(20).mean()).item())

    if sma_5 > sma_20:
        signal = "BUY"
        strength = min((sma_5 - sma_20) / max(sma_20, 1e-9), 1.0)
    elif sma_5 < sma_20:
        signal = "SELL"
        strength = min((sma_20 - sma_5) / max(sma_20, 1e-9), 1.0)
    else:
        signal = "HOLD"
        strength = 0.0

    return {
        "symbol": payload.symbol,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "features": {
            "last": last,
            "sma_5": sma_5,
            "sma_20": sma_20,
        },
        "signal": signal,
        "strength": round(float(strength), 6),
    }
