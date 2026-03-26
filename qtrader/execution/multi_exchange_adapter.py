"""Multi-exchange adapter that routes orders to the best exchange using a smart router."""

import logging
from decimal import Decimal
from typing import Any

from qtrader.core.types import OrderEvent
from qtrader.execution.execution_engine import ExchangeAdapter
from qtrader.execution.smart_router import SmartOrderRouter

logger = logging.getLogger(__name__)


class MultiExchangeAdapter(ExchangeAdapter):
    """
    An exchange adapter that routes orders to the best exchange based on a smart router.
    This adapter implements the ExchangeAdapter interface by delegating to selected
    exchange adapters.
    """

    def __init__(
        self,
        exchanges: dict[str, ExchangeAdapter],
        router: SmartOrderRouter,
        name: str = "MultiExchangeAdapter",
    ):
        """
        Initialize multi-exchange adapter.

        Args:
            exchanges: Dictionary mapping exchange name to exchange adapter instance
            router: SmartOrderRouter instance for selecting exchanges
            name: Name of this adapter
        """
        super().__init__(name=name)
        self.exchanges = exchanges
        self.router = router
        self.logger = logger.getChild("MultiExchangeAdapter")
        self.logger.info(f"MultiExchangeAdapter initialized with {len(exchanges)} exchanges")

    async def _gather_market_data(self, symbol: str) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Decimal]], dict[str, float]]:
        """Gather market data, fees, and latency from all exchanges for a symbol."""
        market_data = {}
        fees_data = {}
        latency_data = {}
        for exchange_name, adapter in self.exchanges.items():
            try:
                orderbook = await adapter.get_orderbook(symbol)
                market_data[exchange_name] = orderbook
            except Exception as e:
                self.logger.error(f"Failed to get orderbook from {exchange_name}: {e}")
                market_data[exchange_name] = {"bids": [], "asks": []}
            try:
                fees = await adapter.get_fees(symbol)
                fees_data[exchange_name] = fees
            except Exception as e:
                self.logger.error(f"Failed to get fees from {exchange_name}: {e}")
                fees_data[exchange_name] = {"maker": Decimal('0'), "taker": Decimal('0')}
            # Latency data is not yet available; default to 0
            latency_data[exchange_name] = 0.0
        return market_data, fees_data, latency_data

    async def send_order(self, order: OrderEvent) -> tuple[bool, str | None]:
        """
        Send an order to the best exchange as determined by the router.

        Args:
            order: OrderEvent to send

        Returns:
            Tuple (success, order_id or error_message)
        """
        # We need market data, fees, and latency data for the router.
        # Gather from all exchanges for the symbol being traded.
        market_data, fees_data, latency_data = await self._gather_market_data(order.symbol)

        # Select the best exchange
        try:
            exchange_name = self.router._select_smart_exchange(
                order, market_data, fees_data, latency_data
            )
        except Exception as e:
            self.logger.error(f"Error selecting exchange: {e}")
            # Fallback to the first exchange
            exchange_name = list(self.exchanges.keys())[0] if self.exchanges else None

        if not exchange_name or exchange_name not in self.exchanges:
            error_msg = "No valid exchange available for routing"
            self.logger.error(error_msg)
            return False, error_msg

        # Prepare list of exchanges to try, starting with the selected one
        exchanges_to_try = [exchange_name] + [name for name in self.exchanges.keys() if name != exchange_name]
        for exch_name in exchanges_to_try:
            adapter = self.exchanges[exch_name]
            self.logger.debug(f"Attempting to send order {order.order_id} to {exch_name}")
            success, result = await adapter.send_order(order)
            if success:
                self.logger.info(f"Order sent successfully to {exch_name}")
                return True, result
            else:
                self.logger.warning(f"Failed to send order to {exch_name}: {result}")
        # All exchanges failed
        error_msg = "All exchanges failed to send order"
        self.logger.error(error_msg)
        return False, error_msg

    async def cancel_order(self, order_id: str) -> tuple[bool, str | None]:
        """
        Cancel an order. We need to know which exchange the order was sent to.
        In a real system, we would store the exchange associated with each order ID.
        For now, we'll try all exchanges until we find one that can cancel the order.
        """
        self.logger.info(f"Attempting to cancel order {order_id}")
        # Try each exchange until we find one that can cancel the order
        for exchange_name, exchange_adapter in self.exchanges.items():
            try:
                success, error = await exchange_adapter.cancel_order(order_id)
                if success:
                    self.logger.info(f"Order {order_id} cancelled on {exchange_name}")
                    return True, None
                else:
                    self.logger.debug(
                        f"Exchange {exchange_name} failed to cancel order {order_id}: {error}"
                    )
            except Exception as e:
                self.logger.error(
                    f"Error cancelling order {order_id} on {exchange_name}: {e}"
                )
        # If none succeeded
        error_msg = f"Order {order_id} not found or could not be cancelled on any exchange"
        self.logger.warning(error_msg)
        return False, error_msg

    async def get_position(self, symbol: str) -> Decimal:
        """
        Get the total position across all exchanges for a symbol.
        """
        total_position = Decimal('0')
        for exchange_name, exchange_adapter in self.exchanges.items():
            try:
                pos = await exchange_adapter.get_position(symbol)
                total_position += pos
                self.logger.debug(
                    f"Position from {exchange_name} for {symbol}: {pos}"
                )
            except Exception as e:
                self.logger.error(
                    f"Error getting position for {symbol} from {exchange_name}: {e}"
                )
        self.logger.info(f"Total position for {symbol}: {total_position}")
        return total_position

    # Additional methods for the smart router to get market data, etc.
    async def get_positions(self) -> dict[str, Decimal]:
        """Get current positions from all exchanges."""
        all_positions: dict[str, Decimal] = {}
        for exchange_name, exchange_adapter in self.exchanges.items():
            try:
                positions = await exchange_adapter.get_positions()
                for symbol, pos in positions.items():
                    all_positions[symbol] = all_positions.get(symbol, Decimal('0')) + pos
            except Exception as e:
                self.logger.error(
                    f"Error getting positions from {exchange_name}: {e}"
                )
        return all_positions

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """
        Get orderbook for a symbol. We'll return the orderbook from the first exchange
        that has data. In a real system, we might merge orderbooks.
        """
        for exchange_name, exchange_adapter in self.exchanges.items():
            try:
                orderbook = await exchange_adapter.get_orderbook(symbol)
                if orderbook:
                    return orderbook
            except Exception as e:
                self.logger.error(
                    f"Error getting orderbook for {symbol} from {exchange_name}: {e}"
                )
        return {}

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        """
        Get trading fees for a symbol. We'll return the fees from the first exchange.
        In a real system, we might need to specify which exchange we are trading on.
        """
        for exchange_name, exchange_adapter in self.exchanges.items():
            try:
                fees = await exchange_adapter.get_fees(symbol)
                if fees:
                    return fees
            except Exception as e:
                self.logger.error(
                    f"Error getting fees for {symbol} from {exchange_name}: {e}"
                )
        return {}