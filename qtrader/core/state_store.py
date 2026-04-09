from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from qtrader.core.state_replication import StateReplicator
from qtrader.core.config import settings

try:
    import redis.asyncio as redis
except ImportError:
    redis = None
logger = logging.getLogger(__name__)
MAX_EQUITY_CURVE_POINTS = 100000
MAX_ACTIVE_ORDERS = 10000
MAX_POSITIONS = 5000


@dataclass(slots=True)
class Position:
    symbol: str
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    market_value: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def copy(self) -> Position:
        return Position(
            symbol=self.symbol,
            quantity=self.quantity,
            average_price=self.average_price,
            market_value=self.market_value,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            timestamp=self.timestamp,
        )


@dataclass(slots=True)
class Order:
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "PENDING"

    def copy(self) -> Order:
        return Order(
            order_id=self.order_id,
            symbol=self.symbol,
            side=self.side,
            order_type=self.order_type,
            quantity=self.quantity,
            price=self.price,
            timestamp=self.timestamp,
            status=self.status,
        )


@dataclass(slots=True)
class RiskState:
    portfolio_var: Decimal = Decimal("0")
    portfolio_volatility: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    leverage: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def copy(self) -> RiskState:
        return RiskState(
            portfolio_var=self.portfolio_var,
            portfolio_volatility=self.portfolio_volatility,
            max_drawdown=self.max_drawdown,
            leverage=self.leverage,
            daily_pnl=self.daily_pnl,
            timestamp=self.timestamp,
        )


@dataclass(slots=True)
class SystemState:
    version: int = 0
    positions: dict[str, Position] = field(default_factory=dict)
    portfolio_value: Decimal = Decimal("0")
    equity_curve: deque[tuple[datetime, Decimal]] = field(
        default_factory=lambda: deque(maxlen=MAX_EQUITY_CURVE_POINTS)
    )
    active_orders: dict[str, Order] = field(default_factory=dict)
    risk_state: RiskState = field(default_factory=RiskState)
    last_approved_risk_metrics: dict[str, Any] = field(default_factory=dict)
    current_risk_multiplier: Decimal = Decimal("1.0")
    last_signal_timestamp: datetime | None = None
    cash: Decimal = Decimal("0")
    total_fees: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class StateStore:
    def __init__(
        self,
        max_equity_points: int = MAX_EQUITY_CURVE_POINTS,
        max_active_orders: int = MAX_ACTIVE_ORDERS,
        max_positions: int = MAX_POSITIONS,
        replicator: StateReplicator | None = None,
    ) -> None:
        self._state = SystemState()
        self._state.equity_curve = deque(maxlen=max_equity_points)
        self._lock = asyncio.Lock()
        self._logger = logger
        self._max_equity_points = max_equity_points
        self._max_active_orders = max_active_orders
        self._max_positions = max_positions
        self._replicator = replicator
        self._redis: Any = None
        self._use_redis = False
        if redis and settings.redis_host:
            try:
                self._redis = redis.Redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    password=settings.redis_password,
                    db=settings.redis_db,
                    decode_responses=True,
                )
                self._use_redis = True
                self._logger.info(
                    f"STATE_STORE | Connected to Redis at {settings.redis_host}:{settings.redis_port}"
                )
            except Exception as e:
                self._logger.error(f"STATE_STORE | Failed to connect to Redis: {e}")

    async def sync_from_remote(self) -> None:
        if not self._use_redis or not self._redis:
            return
        try:
            pos_data = await self._redis.hgetall(f"{settings.redis_prefix}:positions")
            if pos_data:
                async with self._lock:
                    for sym, data_json in pos_data.items():
                        d = json.loads(data_json)
                        self._state.positions[sym] = Position(
                            symbol=sym,
                            quantity=Decimal(d["quantity"]),
                            average_price=Decimal(d["average_price"]),
                            timestamp=datetime.fromisoformat(d["timestamp"]),
                        )
            val = await self._redis.get(f"{settings.redis_prefix}:portfolio_value")
            if val:
                async with self._lock:
                    self._state.portfolio_value = Decimal(val)
            self._logger.info("STATE_STORE | Synced state from Redis")
        except Exception as e:
            self._logger.error(f"STATE_STORE | Remote sync failed: {e}")

    async def _update_redis_position(self, symbol: str, position: Position) -> None:
        if self._use_redis and self._redis:
            data = {
                "quantity": str(position.quantity),
                "average_price": str(position.average_price),
                "timestamp": position.timestamp.isoformat(),
            }
            await self._redis.hset(f"{settings.redis_prefix}:positions", symbol, json.dumps(data))

    async def _update_redis_portfolio_value(self, value: Decimal) -> None:
        if self._use_redis and self._redis:
            await self._redis.set(f"{settings.redis_prefix}:portfolio_value", str(value))

    async def get_positions(self) -> dict[str, Position]:
        async with self._lock:
            return {sym: pos.copy() for (sym, pos) in self._state.positions.items()}

    async def get_position(self, symbol: str) -> Position | None:
        async with self._lock:
            position = self._state.positions.get(symbol)
            return position.copy() if position else None

    async def set_position(self, position: Position) -> None:
        async with self._lock:
            if len(self._state.positions) >= self._max_positions:
                self._logger.warning(
                    f"STATE_STORE | Position limit reached ({self._max_positions}). Rejecting new position for {position.symbol}"
                )
                return
            self._state.positions[position.symbol] = position.copy()
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
            await self._update_redis_position(position.symbol, position)
        self._publish_if_primary()

    async def update_position(
        self, symbol: str, quantity_delta: Decimal, avg_price: Decimal
    ) -> None:
        async with self._lock:
            existing = self._state.positions.get(symbol)
            if existing:
                new_qty = existing.quantity + quantity_delta
                if new_qty == 0:
                    self._state.positions.pop(symbol, None)
                else:
                    total_cost = existing.average_price * abs(existing.quantity) + avg_price * abs(
                        quantity_delta
                    )
                    existing.quantity = new_qty
                    existing.average_price = (
                        total_cost / abs(new_qty) if new_qty != 0 else Decimal("0")
                    )
                    existing.timestamp = datetime.now(timezone.utc)
            elif quantity_delta != 0:
                self._state.positions[symbol] = Position(
                    symbol=symbol,
                    quantity=quantity_delta,
                    average_price=avg_price,
                    timestamp=datetime.now(timezone.utc),
                )
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
        self._publish_if_primary()

    def _publish_if_primary(self) -> None:
        if self._replicator and self._replicator.state.local_role.value == "PRIMARY":
            self._replicator.publish_state(self._snapshot_state())

    async def get_portfolio_value(self) -> Decimal:
        async with self._lock:
            return self._state.portfolio_value

    async def set_portfolio_value(self, value: Decimal) -> None:
        async with self._lock:
            self._state.portfolio_value = value
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
            await self._update_redis_portfolio_value(value)
        self._publish_if_primary()

    async def get_equity_curve(self) -> list[tuple[datetime, Decimal]]:
        async with self._lock:
            return list(self._state.equity_curve)

    async def append_to_equity_curve(self, timestamp: datetime, value: Decimal) -> None:
        async with self._lock:
            self._state.equity_curve.append((timestamp, value))
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
        self._publish_if_primary()

    async def get_active_orders(self) -> dict[str, Order]:
        async with self._lock:
            return {oid: order.copy() for (oid, order) in self._state.active_orders.items()}

    async def set_order(self, order: Order) -> None:
        async with self._lock:
            if len(self._state.active_orders) >= self._max_active_orders:
                self._logger.warning(
                    f"STATE_STORE | Active order limit reached ({self._max_active_orders}). Rejecting order {order.order_id}"
                )
                return
            self._state.active_orders[order.order_id] = order.copy()
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
        self._publish_if_primary()

    async def update_order(self, order_id: str, transform: Callable[[Order], None]) -> None:
        async with self._lock:
            order = self._state.active_orders.get(order_id)
            if order:
                transform(order)
                self._state.version += 1
                self._state.timestamp = datetime.now(timezone.utc)
        self._publish_if_primary()

    async def remove_order(self, order_id: str) -> None:
        async with self._lock:
            self._state.active_orders.pop(order_id, None)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
        self._publish_if_primary()

    async def get_risk_state(self) -> RiskState:
        async with self._lock:
            return self._state.risk_state.copy()

    async def set_risk_state(self, risk_state: RiskState) -> None:
        async with self._lock:
            self._state.risk_state = risk_state.copy()
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_system_state(self) -> SystemState:
        async with self._lock:
            return SystemState(
                version=self._state.version,
                positions={sym: pos.copy() for (sym, pos) in self._state.positions.items()},
                portfolio_value=self._state.portfolio_value,
                equity_curve=deque(self._state.equity_curve, maxlen=self._max_equity_points),
                active_orders={
                    oid: order.copy() for (oid, order) in self._state.active_orders.items()
                },
                risk_state=self._state.risk_state.copy(),
                last_approved_risk_metrics=dict(self._state.last_approved_risk_metrics),
                current_risk_multiplier=self._state.current_risk_multiplier,
                last_signal_timestamp=self._state.last_signal_timestamp,
                cash=self._state.cash,
                total_fees=self._state.total_fees,
                timestamp=self._state.timestamp,
            )

    async def set_last_approved_risk_metrics(self, metrics: dict[str, Any]) -> None:
        async with self._lock:
            self._state.last_approved_risk_metrics = dict(metrics)
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_last_approved_risk_metrics(self) -> dict[str, Any]:
        async with self._lock:
            return dict(self._state.last_approved_risk_metrics)

    async def set_current_risk_multiplier(self, multiplier: Decimal) -> None:
        async with self._lock:
            self._state.current_risk_multiplier = multiplier
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def get_last_signal_timestamp(self) -> datetime | None:
        async with self._lock:
            return self._state.last_signal_timestamp

    async def set_last_signal_timestamp(self, ts: datetime) -> None:
        async with self._lock:
            self._state.last_signal_timestamp = ts
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)

    async def update_performance_metrics(
        self, symbol: str, quantity: Decimal, price: Decimal
    ) -> None:
        async with self._lock:
            pnl_impact = price * abs(quantity) * Decimal("0.0001")
            self._state.portfolio_value += pnl_impact
            self._state.version += 1
            self._state.timestamp = datetime.now(timezone.utc)
            self._logger.info(f"PERFORMANCE_SYNC | {symbol} | NAV: {self._state.portfolio_value}")

    def get_version(self) -> int:
        return self._state.version

    def get_memory_stats(self) -> dict[str, Any]:
        return {
            "equity_curve_points": len(self._state.equity_curve),
            "max_equity_curve_points": self._max_equity_points,
            "equity_curve_usage_pct": round(
                len(self._state.equity_curve) / self._max_equity_points * 100, 1
            ),
            "active_orders": len(self._state.active_orders),
            "max_active_orders": self._max_active_orders,
            "positions": len(self._state.positions),
            "max_positions": self._max_positions,
            "state_version": self._state.version,
            "replicator_role": self._replicator.state.local_role.value
            if self._replicator
            else "NONE",
        }

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "version": self._state.version,
            "positions": {
                sym: {
                    "quantity": str(pos.quantity),
                    "average_price": str(pos.average_price),
                    "market_value": str(pos.market_value),
                }
                for (sym, pos) in self._state.positions.items()
            },
            "active_orders": {
                oid: {
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": str(order.quantity),
                    "status": order.status,
                }
                for (oid, order) in self._state.active_orders.items()
            },
            "portfolio_value": str(self._state.portfolio_value),
            "cash": str(self._state.cash),
            "risk_state": {
                "portfolio_var": str(self._state.risk_state.portfolio_var),
                "max_drawdown": str(self._state.risk_state.max_drawdown),
                "leverage": str(self._state.risk_state.leverage),
            },
            "timestamp": self._state.timestamp.isoformat(),
        }
