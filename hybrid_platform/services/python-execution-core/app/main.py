from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="python-execution-core", version="0.1.0")


class ExecuteOrderRequest(BaseModel):
    order_id: str
    symbol: str
    side: str
    qty: float = Field(gt=0)
    price: float | None = None
    order_type: str = "MARKET"
    idempotency_key: str
    trace_id: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"service": "python-execution-core", "status": "ok"}


@app.post("/execute")
async def execute(payload: ExecuteOrderRequest) -> dict[str, Any]:
    # Stub for Rust bridge integration point.
    ref_price = Decimal(str(payload.price if payload.price is not None else 65000.0))
    fee_rate = Decimal("0.0004")
    qty = Decimal(str(payload.qty))
    notional = qty * ref_price
    fee = notional * fee_rate

    risk_flag = "OK"
    if notional > Decimal("100000"):
        risk_flag = "REVIEW"

    return {
        "status": "filled_stub",
        "order_id": payload.order_id,
        "symbol": payload.symbol,
        "side": payload.side,
        "qty": float(qty),
        "fill_price": float(ref_price),
        "fee": float(fee),
        "risk_flag": risk_flag,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": payload.trace_id,
    }
