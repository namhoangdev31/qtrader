"""Volume-Weighted Average Price execution algorithm."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from qtrader.core.event import OrderEvent

from qtrader.output.execution.algos.base import ChildOrder

__all__ = ["VWAPAlgo"]

_LOG = logging.getLogger("qtrader.output.execution.algos.vwap")


@dataclass(slots=True)
class VWAPAlgo:
    """Volume-Weighted Average Price. Schedule child orders proportional to historical volume profile.

    Attributes:
        volume_profile: List of T weights (sum=1) representing intraday volume distribution.
    """

    volume_profile: list[float]

    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]:
        """Schedule child orders so that quantity follows the volume profile.

        Args:
            order: Parent order with symbol, side, quantity.
            context: Optional dict; may contain "now" (unix timestamp).

        Returns:
            List of child orders with quantities proportional to volume_profile.
        """
        if not self.volume_profile:
            _LOG.warning("VWAP: empty volume_profile")
            return []

        now = float(context.get("now", time.time()))
        total_qty = order.quantity
        side = order.side
        symbol = order.symbol
        parent_id = order.order_id or "vwap"
        T = len(self.volume_profile)
        total_weight = sum(self.volume_profile)
        if total_weight <= 0:
            return []

        interval_seconds = 3600.0 / T if T > 0 else 3600.0
        children: list[ChildOrder] = []

        for i, w in enumerate(self.volume_profile):
            qty = total_qty * (w / total_weight)
            if qty <= 0:
                continue
            scheduled_at = now + i * interval_seconds
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
def test_vwap_profile_quantities() -> None:
    from qtrader.core.event import OrderEvent, EventType
    order = OrderEvent(type=EventType.ORDER, symbol="A", order_type="MARKET", quantity=100.0, side="BUY")
    algo = VWAPAlgo(volume_profile=[0.2, 0.3, 0.5])
    children = algo.schedule(order, {"now": 0.0})
    total = sum(c.quantity for c in children)
    assert abs(total - 100.0) < 1e-6
"""
