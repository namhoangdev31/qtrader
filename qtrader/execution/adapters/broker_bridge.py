"""Bridge adapter to convert BrokerAdapter to ExchangeAdapter interface."""

import logging
from decimal import Decimal
from typing import Any

from qtrader.core.types import OrderEvent
from qtrader.execution.brokers.base import BrokerAdapter
from qtrader.execution.execution_engine import ExchangeAdapter

logger = logging.getLogger(__name__)


class BrokerAdapterBridge(ExchangeAdapter):
    """
    Adapter that wraps a BrokerAdapter to conform to ExchangeAdapter interface.
    This allows ExecutionEngine to use real broker adapters (e.g., BinanceBrokerAdapter).
    """

    def __init__(self, broker: BrokerAdapter, name: str) -> None:
        """
        Initialize bridge adapter.

        Args:
            broker: The underlying broker adapter
            name: Name for this adapter (e.g., "Binance")
        """
        super().__init__(name=name)
        self.broker = broker
        self.logger = logger.getChild(f"BrokerAdapterBridge.{name}")

    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """
        Send order via the underlying broker adapter.

        Args:
            order: OrderEvent to send

        Returns:
            Tuple (success, order_id or error_message)
        """
        try:
            broker_oid = await self.broker.submit_order(order)
            self.logger.info(f"Order sent via broker {self.name}, broker order ID: {broker_oid}")
            return True, broker_oid
        except Exception as e:
            self.logger.error(f"Error sending order via broker {self.name}: {e}")
            return False, str(e)

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """
        Cancel order via the underlying broker adapter.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            Tuple (success, error_message)
        """
        try:
            success = await self.broker.cancel_order(order_id)
            if success:
                self.logger.info(f"Order {order_id} cancelled via broker {self.name}")
                return True, None
            else:
                error_msg = f"Broker {self.name} failed to cancel order {order_id}"
                self.logger.warning(error_msg)
                return False, error_msg
        except Exception as e:
            self.logger.error(f"Error cancelling order {order_id} via broker {self.name}: {e}")
            return False, str(e)

    async def get_position(self, symbol: str) -> Decimal:
        """
        Get position for a symbol via broker adapter.
        Note: BrokerAdapter protocol does not have get_position method.
        We'll need to implement via get_balance and map.
        For now, return 0 as placeholder.
        """
        self.logger.warning(f"get_position not implemented for broker {self.name}, returning 0")
        return Decimal('0')

    async def get_positions(self) -> dict[str, Decimal]:
        """
        Get all positions via broker adapter.
        Placeholder implementation.
        """
        self.logger.warning(f"get_positions not implemented for broker {self.name}, returning empty")
        return {}

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """
        Get orderbook via broker adapter if supported.
        Placeholder implementation.
        """
        self.logger.warning(f"get_orderbook not implemented for broker {self.name}, returning empty")
        return {"bids": [], "asks": []}

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        """
        Get fees via broker adapter if supported.
        Placeholder implementation.
        """
        self.logger.warning(f"get_fees not implemented for broker {self.name}, returning zero fees")
        return {"maker": Decimal('0'), "taker": Decimal('0')}