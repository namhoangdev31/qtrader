"""Multi-exchange adapter that routes orders to the best exchange using a smart router."""

import asyncio
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
    ) -> None:
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

    async def _gather_market_data(
        self, symbol: str
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Decimal]], dict[str, float]]:
        """Gather market data, fees, and latency from all exchanges for a symbol.

        Uses asyncio.gather() for parallel execution across venues (Standash §2.5).
        """

        async def _fetch_orderbook(
            name: str, adapter: ExchangeAdapter
        ) -> tuple[str, dict[str, Any]]:
            try:
                orderbook = await adapter.get_orderbook(symbol)
                return name, orderbook
            except Exception as e:
                self.logger.error(f"Failed to get orderbook from {name}: {e}")
                return name, {"bids": [], "asks": []}

        async def _fetch_fees(
            name: str, adapter: ExchangeAdapter
        ) -> tuple[str, dict[str, Decimal]]:
            try:
                fees = await adapter.get_fees(symbol)
                return name, fees
            except Exception as e:
                self.logger.error(f"Failed to get fees from {name}: {e}")
                return name, {"maker": Decimal("0"), "taker": Decimal("0")}

        # Parallel execution: all venues queried simultaneously
        orderbook_results, fees_results = await asyncio.gather(
            asyncio.gather(*[_fetch_orderbook(n, a) for n, a in self.exchanges.items()]),
            asyncio.gather(*[_fetch_fees(n, a) for n, a in self.exchanges.items()]),
        )

        market_data = dict(orderbook_results)
        fees_data = dict(fees_results)
        latency_data = {name: 0.0 for name in self.exchanges}
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
            exchange_name = next(iter(self.exchanges.keys())) if self.exchanges else None

        if not exchange_name or exchange_name not in self.exchanges:
            error_msg = "No valid exchange available for routing"
            self.logger.error(error_msg)
            return False, error_msg

        # Prepare list of exchanges to try, starting with the selected one
        exchanges_to_try = [exchange_name] + [
            name for name in self.exchanges.keys() if name != exchange_name
        ]
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
                self.logger.error(f"Error cancelling order {order_id} on {exchange_name}: {e}")
        # If none succeeded
        error_msg = f"Order {order_id} not found or could not be cancelled on any exchange"
        self.logger.warning(error_msg)
        return False, error_msg

    async def get_position(self, symbol: str) -> Decimal:
        """
        Get the total position across all exchanges for a symbol.
        Uses asyncio.gather() for parallel position queries.
        """

        async def _fetch_pos(name: str, adapter: ExchangeAdapter) -> Decimal:
            try:
                return await adapter.get_position(symbol)
            except Exception as e:
                self.logger.error(f"Error getting position for {symbol} from {name}: {e}")
                return Decimal("0")

        # Parallel: query all exchanges simultaneously
        results = await asyncio.gather(*[_fetch_pos(n, a) for n, a in self.exchanges.items()])
        total_position = sum(results, Decimal("0"))
        self.logger.info(f"Total position for {symbol}: {total_position}")
        return total_position

    # Additional methods for the smart router to get market data, etc.
    async def get_positions(self) -> dict[str, Decimal]:
        """Get current positions from all exchanges using parallel queries."""

        async def _fetch_positions(name: str, adapter: ExchangeAdapter) -> dict[str, Decimal]:
            try:
                return await adapter.get_positions()
            except Exception as e:
                self.logger.error(f"Error getting positions from {name}: {e}")
                return {}

        # Parallel: query all exchanges simultaneously
        results = await asyncio.gather(*[_fetch_positions(n, a) for n, a in self.exchanges.items()])
        all_positions: dict[str, Decimal] = {}
        for positions in results:
            for symbol, pos in positions.items():
                all_positions[symbol] = all_positions.get(symbol, Decimal("0")) + pos
        return all_positions

    async def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """
        Get orderbook for a symbol. We'll return the orderbook from the first exchange
        that has data. In a real system, we might merge orderbooks.
        Uses asyncio.gather() for parallel queries.
        """

        async def _fetch_orderbook(name: str, adapter: ExchangeAdapter) -> dict[str, Any]:
            try:
                return await adapter.get_orderbook(symbol)
            except Exception as e:
                self.logger.error(f"Error getting orderbook for {symbol} from {name}: {e}")
                return {}

        # Parallel: query all exchanges simultaneously
        results = await asyncio.gather(*[_fetch_orderbook(n, a) for n, a in self.exchanges.items()])
        for orderbook in results:
            if orderbook:
                return orderbook
        return {}

    async def get_fees(self, symbol: str) -> dict[str, Decimal]:
        """
        Get trading fees for a symbol. We'll return the fees from the first exchange.
        In a real system, we might need to specify which exchange we are trading on.
        Uses asyncio.gather() for parallel queries.
        """

        async def _fetch_fees(name: str, adapter: ExchangeAdapter) -> dict[str, Decimal]:
            try:
                return await adapter.get_fees(symbol)
            except Exception as e:
                self.logger.error(f"Error getting fees for {symbol} from {name}: {e}")
                return {}

        # Parallel: query all exchanges simultaneously
        results = await asyncio.gather(*[_fetch_fees(n, a) for n, a in self.exchanges.items()])
        for fees in results:
            if fees:
                return fees
        return {}
