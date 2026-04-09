from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import polars as pl
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title='python-alpha-feature', version='2.0.0')


class FeatureRequest(BaseModel):
    symbol: str
    closes: list[float] = Field(default_factory=list)


@app.get('/health')
async def health() -> dict[str, str]:
    return {'service': 'python-alpha-feature', 'status': 'ok'}


@app.post('/features')
async def features(payload: FeatureRequest) -> dict[str, Any]:
    if not payload.closes:
        return {
            'symbol': payload.symbol,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'features': {},
        }

    frame = pl.DataFrame({'close': payload.closes})
    sma_5 = float(frame.select(pl.col('close').tail(5).mean()).item())
    sma_20 = float(frame.select(pl.col('close').tail(20).mean()).item())

    return {
        'symbol': payload.symbol,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'features': {
            'sma_5': sma_5,
            'sma_20': sma_20,
            'trend': 'UP' if sma_5 > sma_20 else 'DOWN' if sma_5 < sma_20 else 'FLAT',
        },
    }
