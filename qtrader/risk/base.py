from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from qtrader.core.events import OrderEvent, RiskEvent


class RiskModule(ABC):
    @abstractmethod
    def evaluate(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


@runtime_checkable
class PositionSizer(Protocol):
    def calculate_quantity(self, symbol: str, price: float, signal_strength: float) -> float: ...


@runtime_checkable
class RiskManager(Protocol):
    def check_order(self, order: OrderEvent) -> RiskEvent | None: ...
