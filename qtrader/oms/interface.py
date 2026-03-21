from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from qtrader.core.event import OrderEvent, FillEvent


class OMSInterface(ABC):
    """Interface for the Order Management System."""

    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> str:
        """
        Submit an order to the exchange.

        Args:
            order: The order to submit.

        Returns:
            The order ID from the exchange.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by its ID.

        Args:
            order_id: The ID of the order to cancel.

        Returns:
            True if the order was cancelled, False otherwise.
        """
        pass

    @abstractmethod
    async def get_fills(self) -> List[FillEvent]:
        """
        Get a list of fills since the last call.

        Returns:
            A list of FillEvent objects.
        """
        pass

    @abstractmethod
    def get_positions(self) -> dict[str, float]:
        """
        Get current positions.

        Returns:
            A dictionary mapping symbol to net quantity (positive=long, negative=short).
        """
        pass

    @abstractmethod
    def get_cash(self) -> float:
        """
        Get current cash balance.

        Returns:
            Cash balance in the account currency.
        """
        pass