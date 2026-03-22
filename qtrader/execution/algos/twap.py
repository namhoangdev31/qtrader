"""Time-Weighted Average Price execution algorithm."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from qtrader.core.event import OrderEvent

from qtrader.execution.algos.base import ChildOrder

__all__ = ["TWAPAlgo"]

_LOG = logging.getLogger("qtrader.execution.algos.twap")


@dataclass(slots=True)
class TWAPAlgo:
    """Time-Weighted Average Price. Splits order into N equal slices over T seconds.

    Attributes:
        duration_seconds: Total duration over which to spread the order.
        slice_count: Number of child orders to create.
    """

    duration_seconds: int
    slice_count: int

    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]:
        """Schedule child orders evenly over the duration.

        Args:
            order: Parent order with symbol, side, quantity.
            context: Optional dict; may contain "now" (unix timestamp) for determinism.

        Returns:
            List of child orders; last slice gets any remainder from rounding.
        """
        if self.slice_count <= 0 or self.duration_seconds <= 0:
            _LOG.warning("TWAP: invalid slice_count or duration_seconds")
            return []

        now = float(context.get("now", time.time()))
        interval = float(self.duration_seconds) / float(self.slice_count)
        total_qty = order.quantity
        side = order.side
        symbol = order.symbol
        parent_id = order.order_id or "twap"

        base_qty = total_qty / self.slice_count
        remainder = total_qty - (base_qty * (self.slice_count - 1))
        children: list[ChildOrder] = []

        for i in range(self.slice_count):
            qty = remainder if i == self.slice_count - 1 else base_qty
            if qty <= 0:
                continue
            scheduled_at = now + i * interval
            children.append(
                ChildOrder(
                    parent_id=parent_id,
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=None,
                    scheduled_at=scheduled_at,
                )
            )

        return children


"""
# Pytest-style examples:
def test_twap_schedule_slice_count() -> None:
    from qtrader.core.event import OrderEvent, EventType
    order = OrderEvent(type=EventType.ORDER, symbol="AAPL", order_type="MARKET", quantity=100.0, side="BUY")
    algo = TWAPAlgo(duration_seconds=60, slice_count=5)
    children = algo.schedule(order, {"now": 1000.0})
    assert len(children) == 5
    assert sum(c.quantity for c in children) == 100.0

def test_twap_weights_sum_to_one() -> None:
    from qtrader.core.event import OrderEvent, EventType
    order = OrderEvent(type=EventType.ORDER, symbol="X", order_type="MARKET", quantity=30.0, side="SELL")
    algo = TWAPAlgo(duration_seconds=300, slice_count=3)
    out = algo.schedule(order, {"now": 0.0})
    assert abs(sum(c.quantity for c in out) - 30.0) < 1e-6
"""
