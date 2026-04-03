from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

from qtrader.backtest.impact import MarketImpactModel
from qtrader.core.bus import EventBus
from qtrader.core.events import FillEvent, MarketEvent, OrderEvent

__all__ = ["FillModel", "SimulatedBroker"]

log = logging.getLogger(__name__)


class FillModel(str, Enum):
    """Fill model specifying how simulated execution prices are chosen."""

    LAST_PRICE = "last_price"
    NEXT_OPEN = "next_open"
    VWAP = "vwap"
    IMPACT = "impact"


BarDict = dict[str, float]


@dataclass(slots=True)
class SimulatedBroker:
    """Simulated broker with configurable fill models and slippage.

    Args:
        bus: EventBus used to publish FillEvents.
        commission_rate: Commission rate as fraction of notional (e.g. 0.001 = 10 bps).
        fill_model: Fill model for execution price.
        slippage_bps: Additional slippage in basis points.
        market_impact: Whether to apply :class:`MarketImpactModel` when using IMPACT.
    """

    bus: EventBus
    commission_rate: float = 0.001
    fill_model: FillModel = FillModel.NEXT_OPEN
    slippage_bps: float = 5.0
    market_impact: bool = True
    _latest_bar: dict[str, BarDict] = field(init=False, default_factory=dict)
    _pending_orders: dict[str, OrderEvent] = field(init=False, default_factory=dict)

    async def on_market_data(self, event: MarketEvent) -> None:
        """Handle incoming market data and attempt to fill queued orders."""
        data = event.data
        symbol = event.symbol
        bar = {
            "open": float(data.get("open", 0.0) or 0.0),
            "high": float(data.get("high", 0.0) or 0.0),
            "low": float(data.get("low", 0.0) or 0.0),
            "close": float(data.get("close", 0.0) or 0.0),
            "volume": float(data.get("volume", 0.0) or 0.0),
        }
        self._latest_bar[symbol] = bar

        # Attempt to fill any pending orders when new bar arrives.
        to_fill: list[str] = [
            oid for oid, ord_ in self._pending_orders.items() if ord_.symbol == symbol
        ]
        for oid in to_fill:
            order = self._pending_orders.pop(oid)
            price = self._select_fill_price(symbol)
            price = self._apply_slippage(price, order.side, float(order.quantity))
            await self._execute_fill(order, price)

    async def on_order(self, event: OrderEvent) -> None:
        """Receive a new order and decide whether to fill immediately or queue."""
        symbol = event.symbol
        order_id = event.order_id or str(uuid.uuid4())
        bar = self._latest_bar.get(symbol)

        if self.fill_model == FillModel.LAST_PRICE and bar is not None:
            price = bar.get("close", 0.0)
            price = self._apply_slippage(price, event.side, float(event.quantity))
            await self._execute_fill(event, price)
            return

        # NEXT_OPEN and VWAP fill on next bar; IMPACT uses impact-adjusted price.
        self._pending_orders[order_id] = event

    def _select_fill_price(self, symbol: str) -> float:
        """Select base fill price from the latest bar for a symbol."""
        bar = self._latest_bar.get(symbol)
        if not bar:
            return 0.0

        if self.fill_model == FillModel.NEXT_OPEN:
            return bar.get("open", bar.get("close", 0.0))
        if self.fill_model == FillModel.VWAP:
            high = bar.get("high", 0.0)
            low = bar.get("low", 0.0)
            close = bar.get("close", 0.0)
            open_px = bar.get("open", close)
            return (open_px + high + low + close) / 4.0
        # For IMPACT, start from mid of high/low or close.
        high = bar.get("high", 0.0)
        low = bar.get("low", 0.0)
        close = bar.get("close", 0.0)
        if high > 0.0 and low > 0.0:
            return (high + low) / 2.0
        return close

    def _apply_slippage(self, price: float, side: str, qty: float) -> float:
        """Apply slippage and optional impact to a base price.

        Args:
            price: Base execution price.
            side: \"BUY\" or \"SELL\".
            qty: Order quantity.

        Returns:
            Adjusted fill price.
        """
        if price <= 0.0 or qty <= 0.0:
            return price

        # Base slippage in bps.
        slippage_frac = self.slippage_bps / 10_000.0
        adj_price = price * (1.0 + slippage_frac if side.upper() == "BUY" else 1.0 - slippage_frac)

        if self.fill_model == FillModel.IMPACT and self.market_impact:
            # Simple impact estimate; daily_volume and sigma_daily are placeholders.
            impact_bps = MarketImpactModel.square_root_impact(
                order_size=qty,
                daily_vol=0.0,
                daily_volume=max(qty * 10.0, 1.0),
                sigma_daily=0.02,
            )
            impact_frac = impact_bps / 10_000.0
            if side.upper() == "BUY":
                adj_price *= 1.0 + impact_frac
            else:
                adj_price *= 1.0 - impact_frac
        return adj_price

    async def _execute_fill(self, order: OrderEvent, price: float) -> None:
        """Publish a FillEvent for a filled order."""
        commission = price * float(order.quantity) * self.commission_rate
        fill = FillEvent(
            symbol=order.symbol,
            quantity=order.quantity,
            price=price,
            commission=commission,
            side=order.side,
            order_id=order.order_id or str(uuid.uuid4()),
            fill_id=str(uuid.uuid4()),
        )
        await self.bus.publish(fill)
        log.info(
            "Simulated fill: symbol=%s side=%s qty=%s price=%.4f",
            order.symbol,
            order.side,
            order.quantity,
            price,
        )


if __name__ == "__main__":
    import asyncio as _asyncio

    from qtrader.core.bus import EventBus as _Bus  # type: ignore[reimported]
    from qtrader.core.events import MarketEvent as _Mkt  # type: ignore[reimported]
    from qtrader.core.events import OrderEvent as _Ord

    async def _smoke() -> None:
        _bus = _Bus()
        broker = SimulatedBroker(bus=_bus, fill_model=FillModel.LAST_PRICE)

        md = _Mkt(symbol="BTC", data={"close": 100.0})
        await broker.on_market_data(md)
        order = _Ord(symbol="BTC", order_type="MARKET", quantity=1.0, side="BUY")
        await broker.on_order(order)

    _asyncio.run(_smoke())

