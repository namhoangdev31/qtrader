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


class TransactionLog(BaseModel):
    """Schema for a single trade event."""

    timestamp: str
    symbol: str
    side: str
    quantity: float
    price: float
    pnl: float | None = None
    reason: str | None = None


class TradingUpdate(BaseModel):
    """Unified WebSocket update message."""

    type: Literal["initial_snapshot", "incremental_update"]
    timestamp: str
    positions: list[PositionRow]
    status: StatusResponse
    recent_logs: list[TransactionLog]
    pnl_summary: dict[str, float]


class SimulationConfig(BaseModel):
    """Configuration for the simulation engine."""

    initial_balance: float = Field(1000.0, gt=0, description="Starting balance in USD")
    sl_pct: float = Field(0.02, gt=0, lt=0.5, description="Stop loss percentage")
    tp_pct: float = Field(0.03, gt=0, lt=0.5, description="Take profit percentage")
    tick_interval: float = Field(1.0, gt=0, description="Seconds between price ticks")
    base_price: float = Field(50000.0, gt=0, description="Starting BTC price")


class AdaptiveStats(BaseModel):
    """Adaptive strategy statistics."""

    stop_loss_pct: float
    take_profit_pct: float
    position_size_pct: float
    win_rate: float
    total_wins: int
    total_losses: int
    win_streak: int
    loss_streak: int
    expected_value: float
    max_drawdown_pct: float
    total_trades: int


class TradeRecordResponse(BaseModel):
    """Completed trade record."""

    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: str
    exit_time: str
    pnl: float
    pnl_pct: float
    commission: float
    reason: str
    stop_loss: float
    take_profit: float


class OpenPositionResponse(BaseModel):
    """Active open position."""

    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float
    take_profit: float
    entry_time: str


class SimulationSnapshot(BaseModel):
    """Full simulation state snapshot."""

    equity: float
    cash: float
    realized_pnl: float
    total_commissions: float
    total_gross_pnl: float = 0.0
    current_price: float
    open_positions: list[OpenPositionResponse]
    trade_history: list[TradeRecordResponse]
    adaptive: AdaptiveStats
    peak_equity: float
    max_drawdown: float
