from __future__ import annotations

from typing import Any

import polars as pl
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title='python-risk-quant', version='2.0.0')


class RiskRequest(BaseModel):
    pnl_series: list[float] = Field(default_factory=list)


@app.get('/health')
async def health() -> dict[str, str]:
    return {'service': 'python-risk-quant', 'status': 'ok'}


@app.post('/var')
async def portfolio_var(payload: RiskRequest) -> dict[str, Any]:
    if not payload.pnl_series:
        return {'var_95': 0.0}

    frame = pl.DataFrame({'pnl': payload.pnl_series})
    var_95 = float(frame.select(pl.col('pnl').quantile(0.05)).item())
    return {'var_95': var_95}
