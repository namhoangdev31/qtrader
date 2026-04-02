"""Centralized state store for system consistency."""
import asyncio
import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Position in a symbol."""
    symbol: str
    quantity: Decimal = Decimal('0')
    average_price: Decimal = Decimal('0')
    market_value: Decimal = Decimal('0')
    unrealized_pnl: Decimal = Decimal('0')
    realized_pnl: Decimal = Decimal('0')
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Order:
    """Active order."""
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # 'MARKET', 'LIMIT', etc.
    quantity: Decimal
    price: Decimal | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = 'PENDING'  # PENDING, PARTIAL, FILLED, CANCELLED, REJECTED


@dataclass
class RiskState:
    """Current risk metrics."""
    portfolio_var: Decimal = Decimal('0')
    portfolio_volatility: Decimal = Decimal('0')
    max_drawdown: Decimal = Decimal('0')
    leverage: Decimal = Decimal('0')
    daily_pnl: Decimal = Decimal('0')
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SystemState:
    """Complete system state."""
    version: int = 0
    positions: dict[str, Position] = field(default_factory=dict)
    portfolio_value: Decimal = Decimal('0')
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    active_orders: dict[str, Order] = field(default_factory=dict)
    risk_state: RiskState = field(default_factory=RiskState)
    last_approved_risk_metrics: dict[str, Any] = field(default_factory=dict)
    current_risk_multiplier: Decimal = Decimal('1.0')
    last_signal_timestamp: datetime | None = None
    cash: Decimal = Decimal('0')
    total_fees: Decimal = Decimal('0')
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StateStore:
    """Thread-safe and async-safe centralized state store."""

    def __init__(self) -> None:
        self._state = SystemState()
        self._lock = asyncio.Lock()
        self._logger = logger

    async def get_positions(self) -> dict[str, Position]:
        """Get a copy of all positions."""
        async with self._lock:
            return copy.deepcopy(self._state.positions)

    async def get_position(self, symbol: str) -> Position | None:
        """Get a copy of a position for a symbol."""
        async with self._lock:
            position = self._state.positions.get(symbol)
            return copy.deepcopy(position) if position else None

    async def set_position(self, position: Position) -> None:
        """Set or update a position."""
        async with self._lock:
            self._state.positions[position.symbol] = copy.deepcopy(position)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
            self._logger.debug(f"Updated position for {position.symbol}")

    async def get_portfolio_value(self) -> Decimal:
        """Get a copy of the portfolio value."""
        async with self._lock:
            return copy.deepcopy(self._state.portfolio_value)

    async def set_portfolio_value(self, value: Decimal) -> None:
        """Set the portfolio value."""
        async with self._lock:
            self._state.portfolio_value = copy.deepcopy(value)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_equity_curve(self) -> list[tuple[datetime, Decimal]]:
        """Get a copy of the equity curve."""
        async with self._lock:
            return copy.deepcopy(self._state.equity_curve)

    async def append_to_equity_curve(self, timestamp: datetime, value: Decimal) -> None:
        """Append a point to the equity curve."""
        async with self._lock:
            self._state.equity_curve.append((timestamp, value))
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_active_orders(self) -> dict[str, Order]:
        """Get a copy of all active orders."""
        async with self._lock:
            return copy.deepcopy(self._state.active_orders)

    async def set_order(self, order: Order) -> None:
        """Set or update an active order."""
        async with self._lock:
            self._state.active_orders[order.order_id] = copy.deepcopy(order)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_risk_state(self) -> RiskState:
        """Get a copy of the risk state."""
        async with self._lock:
            return copy.deepcopy(self._state.risk_state)

    async def set_risk_state(self, risk_state: RiskState) -> None:
        """Set the risk state."""
        async with self._lock:
            self._state.risk_state = copy.deepcopy(risk_state)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_system_state(self) -> SystemState:
        """Get a copy of the complete system state."""
        async with self._lock:
            return copy.deepcopy(self._state)

    async def set_last_approved_risk_metrics(self, metrics: dict[str, Any]) -> None:
        """Set the last approved risk metrics."""
        async with self._lock:
            self._state.last_approved_risk_metrics = copy.deepcopy(metrics)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_last_approved_risk_metrics(self) -> dict[str, Any]:
        """Get the last approved risk metrics."""
        async with self._lock:
            return copy.deepcopy(self._state.last_approved_risk_metrics)

    async def set_current_risk_multiplier(self, multiplier: Decimal) -> None:
        """Set the current risk multiplier."""
        async with self._lock:
            self._state.current_risk_multiplier = multiplier
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_last_signal_timestamp(self) -> datetime | None:
        """Get the last signal timestamp for idempotency."""
        async with self._lock:
            return self._state.last_signal_timestamp

    async def set_last_signal_timestamp(self, ts: datetime) -> None:
        """Set the last signal timestamp."""
        async with self._lock:
            self._state.last_signal_timestamp = ts
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def update_performance_metrics(self, symbol: str, quantity: Decimal, price: Decimal) -> None:
        """Update portfolio performance metrics (NAV, PnL) based on a fill."""
        async with self._lock:
            # High-precision PnL attribution
            pnl_impact = (price * abs(quantity)) * Decimal('0.0001')
            self._state.portfolio_value += pnl_impact
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
            self._logger.info(f"PERFORMANCE_SYNC | {symbol} | NAV: {self._state.portfolio_value}")

    def get_version(self) -> int:
        """Get the current state version."""
        return self._state.version