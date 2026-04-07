from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from qtrader.core.events import OrderEvent, RiskEvent


class RiskModule(ABC):
    """Abstract base class for all risk management modules."""

    @abstractmethod
    def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Evaluate risk and return metrics/actions."""
        ...


@runtime_checkable
class PositionSizer(Protocol):
    """Protocol for calculating trade size."""

    def calculate_quantity(self, symbol: str, price: float, signal_strength: float) -> float: ...


@runtime_checkable
class RiskManager(Protocol):
    """Protocol for pre-trade risk checks."""

    def check_order(self, order: OrderEvent) -> RiskEvent | None:
        """Returns a RiskEvent if the order is rejected, else None."""
        ...
