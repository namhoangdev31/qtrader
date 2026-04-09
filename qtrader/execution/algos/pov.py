from __future__ import annotations
import logging
from dataclasses import dataclass
from qtrader.execution.algos.base import ChildOrder

__all__ = ["POVAlgo"]
_LOG = logging.getLogger("qtrader.execution.algos.pov")


@dataclass(slots=True)
class POVAlgo:
    participation_rate: float = 0.05

    async def on_trade(
        self,
        trade_qty: float,
        trade_price: float,
        parent_id: str = "pov",
        symbol: str = "",
        side: str = "BUY",
        remaining_qty: float = 0.0,
    ) -> ChildOrder | None:
        if remaining_qty <= 0 or trade_qty <= 0 or self.participation_rate <= 0:
            return None
        participate_qty = trade_qty * self.participation_rate
        child_qty = min(participate_qty, remaining_qty)
        if child_qty <= 0:
            return None
        import time

        return ChildOrder(
            parent_id=parent_id,
            symbol=symbol,
            side=side,
            quantity=child_qty,
            price=trade_price,
            scheduled_at=time.time(),
        )
