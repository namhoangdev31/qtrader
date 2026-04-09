from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from qtrader.execution.algos.base import ChildOrder

if TYPE_CHECKING:
    from qtrader.core.events import OrderEvent
__all__ = ["TWAPAlgo"]
_LOG = logging.getLogger("qtrader.execution.algos.twap")


@dataclass(slots=True)
class TWAPAlgo:
    duration_seconds: int
    slice_count: int

    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]:
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
        remainder = total_qty - base_qty * (self.slice_count - 1)
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
