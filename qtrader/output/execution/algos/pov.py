"""Percentage of Volume (POV) execution algorithm."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from qtrader.output.execution.algos.base import ChildOrder

__all__ = ["POVAlgo"]

_LOG = logging.getLogger("qtrader.output.execution.algos.pov")


@dataclass(slots=True)
class POVAlgo:
    """Participate at a fixed percentage of market volume. Dynamic schedule driven by trade prints.

    Attributes:
        participation_rate: Fraction of each market trade to participate in (e.g. 0.05 = 5%).
    """

    participation_rate: float = 0.05

    async def on_trade_print(
        self,
        trade_qty: float,
        trade_price: float,
        parent_id: str = "pov",
        symbol: str = "",
        side: str = "BUY",
        remaining_qty: float = 0.0,
    ) -> ChildOrder | None:
        """Emit a child order for a fraction of the market trade, if parent has remaining quantity.

        Args:
            trade_qty: Quantity of the market trade.
            trade_price: Price of the market trade.
            parent_id: Parent order id.
            symbol: Instrument symbol.
            side: "BUY" or "SELL".
            remaining_qty: Remaining quantity to fill for the parent.

        Returns:
            A ChildOrder for participation_rate * trade_qty (capped by remaining_qty), or None if fully filled.
        """
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
