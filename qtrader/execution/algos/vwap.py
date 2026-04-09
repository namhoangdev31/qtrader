from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from qtrader.execution.algos.base import ChildOrder

if TYPE_CHECKING:
    from qtrader.core.events import OrderEvent
__all__ = ["VWAPAlgo"]
_LOG = logging.getLogger("qtrader.execution.algos.vwap")


@dataclass(slots=True)
class VWAPAlgo:
    volume_profile: list[float]

    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]:
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
