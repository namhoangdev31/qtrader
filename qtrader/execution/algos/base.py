from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from qtrader.core.events import OrderEvent
__all__ = ["ChildOrder", "ExecutionAlgo"]


@dataclass(slots=True)
class ChildOrder:
    parent_id: str
    symbol: str
    side: str
    quantity: float
    price: float | None
    scheduled_at: float


class ExecutionAlgo(Protocol):
    def schedule(self, order: OrderEvent, context: dict[str, Any]) -> list[ChildOrder]: ...
