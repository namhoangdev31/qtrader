"""Unified Order Management System with position and P&L tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import polars as pl

from qtrader.core.event import FillEvent, OrderEvent
from qtrader.output.execution.brokers.base import BrokerAdapter

__all__ = ["Position", "PositionManager", "UnifiedOMS"]

_LOG = logging.getLogger("qtrader.oms")


@dataclass(slots=True)
class Position:
    """Single position in one symbol with cost and P&L.

    Attributes:
        symbol: Instrument symbol.
        qty: Net quantity (positive=long, negative=short).
        avg_cost: Average cost per unit.
        realized_pnl: Cumulative realized P&L from closed portion.
    """

    symbol: str
    qty: float
    avg_cost: float
    realized_pnl: float = 0.0

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealized P&L at current price."""
        return (current_price - self.avg_cost) * self.qty


class PositionManager:
    """FIFO position tracking and real-time P&L."""

    def __init__(self) -> None:
        self._lots: dict[str, list[tuple[float, float]]] = {}
        self._realized_pnl: dict[str, float] = {}

    def on_fill(self, fill: FillEvent, current_price: float) -> None:
        """Update positions using FIFO. On reduction, update avg_cost and realized_pnl."""
        sym = fill.symbol
        fill_qty = fill.quantity
        fill_price = fill.price
        side = fill.side.upper()
        signed = fill_qty if side == "BUY" else -fill_qty

        if sym not in self._lots:
            self._lots[sym] = []
            self._realized_pnl[sym] = 0.0

        lots = self._lots[sym]
        if signed > 0:
            lots.append((signed, fill_price))
        else:
            remaining = -signed
            while remaining > 0 and lots:
                lot_qty, lot_price = lots[0]
                if lot_qty <= 0:
                    lots.pop(0)
                    continue
                take = min(remaining, lot_qty)
                self._realized_pnl[sym] += (fill_price - lot_price) * take
                remaining -= take
                if lot_qty == take:
                    lots.pop(0)
                else:
                    lots[0] = (lot_qty - take, lot_price)
            if remaining > 0:
                lots.append((-remaining, fill_price))

    def get_position(self, symbol: str) -> Position | None:
        """Return current position for symbol or None."""
        if symbol not in self._lots:
            return None
        lots = self._lots[symbol]
        total_qty = sum(q for q, _ in lots)
        if total_qty == 0:
            return Position(symbol=symbol, qty=0.0, avg_cost=0.0, realized_pnl=self._realized_pnl.get(symbol, 0.0))
        total_cost = sum(q * p for q, p in lots)
        avg_cost = total_cost / total_qty
        return Position(
            symbol=symbol,
            qty=total_qty,
            avg_cost=avg_cost,
            realized_pnl=self._realized_pnl.get(symbol, 0.0),
        )

    def get_all_positions(self, prices: dict[str, float] | None = None) -> pl.DataFrame:
        """DataFrame with columns: symbol, qty, avg_cost, unrealized_pnl."""
        prices = prices or {}
        rows: list[dict[str, float]] = []
        for symbol in self._lots:
            pos = self.get_position(symbol)
            if pos is None or pos.qty == 0:
                continue
            upnl = pos.unrealized_pnl(prices.get(symbol, pos.avg_cost))
            rows.append({
                "symbol": symbol,
                "qty": pos.qty,
                "avg_cost": pos.avg_cost,
                "unrealized_pnl": upnl,
            })
        if not rows:
            return pl.DataFrame(
                {"symbol": pl.Series([], dtype=pl.String), "qty": pl.Series([], dtype=pl.Float64), "avg_cost": pl.Series([], dtype=pl.Float64), "unrealized_pnl": pl.Series([], dtype=pl.Float64)}
            )
        return pl.DataFrame(rows)

    def get_total_pnl(self, prices: dict[str, float]) -> float:
        """Total P&L (realized + unrealized) across all positions."""
        total = 0.0
        for symbol in set(self._lots) | set(self._realized_pnl):
            pos = self.get_position(symbol)
            if pos is None:
                total += self._realized_pnl.get(symbol, 0.0)
                continue
            total += pos.realized_pnl + pos.unrealized_pnl(prices.get(symbol, pos.avg_cost))
        return total


class UnifiedOMS:
    """Centralized Order Management System with position and P&L."""

    def __init__(self) -> None:
        self.adapters: dict[str, BrokerAdapter] = {}
        self.live_orders: dict[str, OrderEvent] = {}
        self.positions: dict[str, dict[str, float]] = {}
        self.market_state: dict[tuple[str, str], dict[str, Any]] = {}
        self.pending_order_context: dict[str, dict[str, Any]] = {}
        self.position_manager = PositionManager()
        self._log = _LOG

    def add_venue(self, name: str, adapter: BrokerAdapter) -> None:
        self.adapters[name] = adapter
        self.positions[name] = {}

    async def sync_all_balances(self) -> None:
        """Polls all venues for current balances/positions."""
        for name, adapter in self.adapters.items():
            try:
                self.positions[name] = await adapter.get_balance()
            except Exception as e:
                self._log.exception("Failed to sync balances for %s", name, exc_info=e)

    def update_market_state(self, venue: str, symbol: str, state: dict[str, Any]) -> None:
        key = (venue, symbol)
        existing = self.market_state.get(key, {})
        self.market_state[key] = {**existing, **state}

    def get_market_state(self, venue: str, symbol: str) -> dict[str, Any]:
        return self.market_state.get((venue, symbol), {})

    def set_pending_order_context(self, symbol: str, context: dict[str, Any]) -> None:
        self.pending_order_context[symbol] = context

    def get_pending_order_context(self, symbol: str) -> dict[str, Any]:
        return self.pending_order_context.get(symbol, {})

    async def on_fill(self, fill: FillEvent, current_price: float | None = None) -> None:
        """Route fill to position manager. current_price from market_state if not provided."""
        if current_price is None:
            for (_, sym), state in self.market_state.items():
                if sym == fill.symbol:
                    bid = state.get("bid") or 0.0
                    ask = state.get("ask") or 0.0
                    if bid and ask:
                        current_price = (float(bid) + float(ask)) / 2.0
                        break
            else:
                current_price = fill.price
        self.position_manager.on_fill(fill, float(current_price))

    def get_pnl(self, prices: dict[str, float]) -> float:
        """Total P&L across all tracked positions."""
        return self.position_manager.get_total_pnl(prices)

    async def route_order(self, venue: str, order: OrderEvent) -> str:
        if venue not in self.adapters:
            raise ValueError(f"Venue {venue} not found")
        adapter = self.adapters[venue]
        broker_oid = await adapter.submit_order(order)
        self.live_orders[broker_oid] = order
        return broker_oid

    def get_total_exposure(self, asset: str) -> float:
        total = 0.0
        for venue_pos in self.positions.values():
            total += venue_pos.get(asset, 0.0)
        return total


"""
# Pytest-style examples:
def test_position_unrealized_pnl() -> None:
    p = Position(symbol="A", qty=100.0, avg_cost=50.0, realized_pnl=0.0)
    assert p.unrealized_pnl(60.0) == 1000.0

def test_position_manager_get_all_positions() -> None:
    pm = PositionManager()
    df = pm.get_all_positions()
    assert "symbol" in df.columns and "qty" in df.columns
"""
