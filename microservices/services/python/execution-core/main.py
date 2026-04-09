from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title='python-execution-core', version='2.0.0')


class ExecuteOrderRequest(BaseModel):
    order_id: str
    symbol: str
    action: str
    quantity: float = Field(gt=0)
    price: float | None = None
    trace_id: str
    session_id: str | None = None


@app.get('/health')
async def health() -> dict[str, str]:
    return {'service': 'python-execution-core', 'status': 'ok'}


@app.post('/execute')
async def execute(payload: ExecuteOrderRequest) -> dict[str, Any]:
    ref_price = Decimal(str(payload.price if payload.price is not None else 65_000.0))
    qty = Decimal(str(payload.quantity))
    fee_rate = Decimal('0.0004')
    notional = qty * ref_price
    fee = notional * fee_rate

    return {
        'order_id': payload.order_id,
        'status': 'ACK',
        'symbol': payload.symbol,
        'action': payload.action,
        'filled_qty': float(qty),
        'fill_price': float(ref_price),
        'fee': float(fee),
        'trace_id': payload.trace_id,
        'session_id': payload.session_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
