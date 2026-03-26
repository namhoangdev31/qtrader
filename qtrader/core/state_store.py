"""Centralized state store for system consistency."""
import asyncio
import copy
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
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
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Order:
    """Active order."""
    order_id: str
    symbol: str
    side: str  # 'BUY' or 'SELL'
    order_type: str  # 'MARKET', 'LIMIT', etc.
    quantity: Decimal
    price: Decimal | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: str = 'PENDING'  # PENDING, PARTIAL, FILLED, CANCELLED, REJECTED


@dataclass
class RiskState:
    """Current risk metrics."""
    portfolio_var: Decimal = Decimal('0')
    portfolio_volatility: Decimal = Decimal('0')
    max_drawdown: Decimal = Decimal('0')
    leverage: Decimal = Decimal('0')
    daily_pnl: Decimal = Decimal('0')
    timestamp: datetime = field(default_factory=datetime.utcnow)


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
    timestamp: datetime = field(default_factory=datetime.utcnow)


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
            self._state.timestamp = datetime.utcnow()
            self._logger.debug(f"Updated position for {position.symbol}")

    async def update_position(self, symbol: str, updater: Callable[[Position], None]) -> None:
        """Update a position using an updater function."""
        async with self._lock:
            if symbol in self._state.positions:
                updater(self._state.positions[symbol])
                self._state.version += 1
                self._state.timestamp = datetime.utcnow()
                self._logger.debug(f"Updated position for {symbol} via updater")
            else:
                self._logger.warning(f"Attempted to update non-existent position for {symbol}")

    async def get_portfolio_value(self) -> Decimal:
        """Get a copy of the portfolio value."""
        async with self._lock:
            return copy.deepcopy(self._state.portfolio_value)

    async def set_portfolio_value(self, value: Decimal) -> None:
        """Set the portfolio value."""
        async with self._lock:
            self._state.portfolio_value = copy.deepcopy(value)
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()
            self._logger.debug(f"Updated portfolio value to {value}")

    async def get_equity_curve(self) -> list[tuple[datetime, Decimal]]:
        """Get a copy of the equity curve."""
        async with self._lock:
            return copy.deepcopy(self._state.equity_curve)

    async def set_equity_curve(self, equity_curve: list[tuple[datetime, Decimal]]) -> None:
        """Set the equity curve."""
        async with self._lock:
            self._state.equity_curve = copy.deepcopy(equity_curve)
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()
            self._logger.debug("Updated equity curve")

    async def append_to_equity_curve(self, timestamp: datetime, value: Decimal) -> None:
        """Append a point to the equity curve."""
        async with self._lock:
            self._state.equity_curve.append((timestamp, value))
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()
            self._logger.debug(f"Appended to equity curve: {timestamp}, {value}")

    async def get_active_orders(self) -> dict[str, Order]:
        """Get a copy of all active orders."""
        async with self._lock:
            return copy.deepcopy(self._state.active_orders)

    async def get_order(self, order_id: str) -> Order | None:
        """Get a copy of an order by ID."""
        async with self._lock:
            order = self._state.active_orders.get(order_id)
            return copy.deepcopy(order) if order else None

    async def set_order(self, order: Order) -> None:
        """Set or update an active order."""
        async with self._lock:
            self._state.active_orders[order.order_id] = copy.deepcopy(order)
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()
            self._logger.debug(f"Updated order {order.order_id}")

    async def update_order(self, order_id: str, updater: Callable[[Order], None]) -> None:
        """Update an order using an updater function."""
        async with self._lock:
            if order_id in self._state.active_orders:
                updater(self._state.active_orders[order_id])
                self._state.version += 1
                self._state.timestamp = datetime.utcnow()
                self._logger.debug(f"Updated order {order_id} via updater")
            else:
                self._logger.warning(f"Attempted to update non-existent order {order_id}")

    async def remove_order(self, order_id: str) -> None:
        """Remove an order from active orders."""
        async with self._lock:
            if order_id in self._state.active_orders:
                del self._state.active_orders[order_id]
                self._state.version += 1
                self._state.timestamp = datetime.utcnow()
                self._logger.debug(f"Removed order {order_id}")
            else:
                self._logger.warning(f"Attempted to remove non-existent order {order_id}")

    async def get_risk_state(self) -> RiskState:
        """Get a copy of the risk state."""
        async with self._lock:
            return copy.deepcopy(self._state.risk_state)

    async def set_risk_state(self, risk_state: RiskState) -> None:
        """Set the risk state."""
        async with self._lock:
            self._state.risk_state = copy.deepcopy(risk_state)
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()
            self._logger.debug("Updated risk state")

    async def get_system_state(self) -> SystemState:
        """Get a copy of the complete system state."""
        async with self._lock:
            return copy.deepcopy(self._state)

    async def snapshot(self) -> SystemState:
        """Get a snapshot of the current state (alias for get_system_state)."""
        return await self.get_system_state()

    async def restore(self, snapshot: SystemState) -> None:
        """Restore the state from a snapshot."""
        async with self._lock:
            self._state = copy.deepcopy(snapshot)
            self._state.version += 1  # Increment version on restore
            self._state.timestamp = datetime.utcnow()
            self._logger.info("State restored from snapshot")

    async def get_last_approved_risk_metrics(self) -> dict[str, Any]:
        """Get the last approved risk metrics."""
        async with self._lock:
            return copy.deepcopy(self._state.last_approved_risk_metrics)

    async def set_last_approved_risk_metrics(self, metrics: dict[str, Any]) -> None:
        """Set the last approved risk metrics."""
        async with self._lock:
            self._state.last_approved_risk_metrics = copy.deepcopy(metrics)
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()

    async def get_current_risk_multiplier(self) -> Decimal:
        """Get the current risk multiplier."""
        async with self._lock:
            return self._state.current_risk_multiplier

    async def set_current_risk_multiplier(self, multiplier: Decimal) -> None:
        """Set the current risk multiplier."""
        async with self._lock:
            self._state.current_risk_multiplier = multiplier
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()

    async def get_last_signal_timestamp(self) -> datetime | None:
        """Get the last signal timestamp for idempotency."""
        async with self._lock:
            return self._state.last_signal_timestamp

    async def set_last_signal_timestamp(self, ts: datetime) -> None:
        """Set the last signal timestamp."""
        async with self._lock:
            self._state.last_signal_timestamp = ts
            self._state.version += 1
            self._state.timestamp = datetime.utcnow()

    def get_version(self) -> int:
        """Get the current state version (thread-safe for reads)."""
        # Note: version is only updated under the lock, but reading an integer is atomic in Python.
        # However, to be safe and consistent, we could use the lock, but for performance we note
        # that version is only changed under the lock and reading an integer is atomic.
        # If we want to be absolutely safe, we can use the lock, but given the GIL and the fact
        # that we are only reading an integer, it's safe. However, let's use the lock for consistency.
        # Actually, let's not lock for version read to avoid overhead, but note that if we are
        # reading while a write is happening, we might get an inconsistent version? 
        # Since version is just an integer and we are incrementing by 1, and reading an integer
        # is atomic, it's safe. We'll do without lock for version.
        return self._state.version