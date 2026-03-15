"""Execution algorithm protocol and child order model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from qtrader.core.event import OrderEvent

__all__ = ["ChildOrder", "ExecutionAlgo"]


@dataclass(slots=True)
class ChildOrder:
    """A single child order emitted by an execution algorithm.

    Attributes:
        parent_id: Identifier of the parent (algo) order.
        symbol: Instrument symbol.
        side: "BUY" or "SELL".
        quantity: Order quantity.
        price: Limit price, or None for market.
        scheduled_at: Unix timestamp when this child is scheduled to be sent.
    """

    parent_id: str
    symbol: str
    side: str
    quantity: float
    price: float | None
    scheduled_at: float


class ExecutionAlgo(Protocol):
    """Protocol for execution algorithms that split a parent order into child orders."""

    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]:
        """Generate a list of child orders from a parent order.

        Args:
            order: The parent order to slice.
            context: Optional context (e.g. current time, volume profile).

        Returns:
            List of child orders with quantities and scheduled times.
        """
        ...
