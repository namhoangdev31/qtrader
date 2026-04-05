"""Pydantic schemas for QTrader API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class OrderRequest(BaseModel):
    """Schema for submitting a manual paper trading order from UI."""
    symbol: str = Field(..., description="Trading pair symbol (e.g. BTC-USD)")
    side: Literal["BUY", "SELL"] = Field(..., description="Trade side")
    quantity: float = Field(..., gt=0, description="Order quantity")
    order_type: Literal["MARKET"] = Field(
        "MARKET", description="Order type (MARKET only for paper UI)"
    )


class PositionRow(BaseModel):
    """Schema representing an open position."""
    symbol: str
    quantity: float
    average_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class StatusResponse(BaseModel):
    """System status response schema."""
    running: bool
    mode: str
    uptime_s: float
    symbols: list[str]
    stats: dict[str, int | float]
