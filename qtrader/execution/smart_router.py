"""Smart order router for multi-exchange execution."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from qtrader.core.types import OrderEvent

logger = logging.getLogger(__name__)


class SmartOrderRouter:
    """
    Smart order router that routes orders to the best exchange based on:
    - Best price (bid/ask)
    - Liquidity (order book depth)
    - Fees (maker/taker)
    - Latency
    - Supports order splitting for large orders
    """

    def __init__(
        self,
        exchanges: dict[str, Any],  # exchange_name -> exchange adapter instance
        routing_mode: str = "smart",  # "best_price", "smart", "manual"
        max_order_size: Decimal | None = None,  # maximum order size before splitting
        split_size: Decimal | None = None,  # size of each split if max_order_size is set
    ) -> None:
        """
        Initialize smart order router.

        Args:
            exchanges: Dictionary mapping exchange name to exchange adapter instance
            routing_mode: Routing strategy to use
            max_order_size: Maximum order size for a single exchange (if set, orders will be split)
            split_size: Size of each split (if None, defaults to max_order_size)
        """
        self.exchanges = exchanges
        self.routing_mode = routing_mode
        self.max_order_size = max_order_size
        self.split_size = split_size or max_order_size
        self.logger = logger.getChild("SmartOrderRouter")
        self.logger.info(f"SmartOrderRouter initialized with {len(exchanges)} exchanges, mode={routing_mode}")

    async def route_order(
        self,
        order: OrderEvent,
        market_data: dict[str, dict[str, Any]],  # exchange_name -> orderbook (with bids and asks)
        fees_data: dict[str, dict[str, Decimal]] | None = None,  # exchange_name -> {'maker': Decimal, 'taker': Decimal}
        latency_data: dict[str, float] | None = None,  # exchange_name -> latency in seconds
    ) -> list[OrderEvent]:
        """
        Route an order to the best exchange(es).

        Args:
            order: OrderEvent to route
            market_data: Dictionary of exchange name to orderbook data
            fees_data: Optional dictionary of exchange name to fee rates
            latency_data: Optional dictionary of exchange name to latency

        Returns:
            List of OrderEvent objects (possibly split) routed to specific exchanges
        """
        self.logger.info(f"Routing order {order.order_id} for {order.symbol} {order.side} {order.quantity}")

        # If the order is small enough, we don't split
        if self.max_order_size is None or order.quantity <= self.max_order_size:
            routed_orders = await self._route_single_order(order, market_data, fees_data, latency_data)
            return routed_orders
        else:
            # Split the order
            return await self._split_and_route_order(order, market_data, fees_data, latency_data)

    async def _route_single_order(
        self,
        order: OrderEvent,
        market_data: dict[str, dict[str, Any]],
        fees_data: dict[str, dict[str, Decimal]] | None,
        latency_data: dict[str, float] | None,
    ) -> list[OrderEvent]:
        """Route a single order (no splitting) to the best exchange."""
        if self.routing_mode == "manual":
            # In manual mode, we rely on the order's metadata to specify the exchange
            exchange_name = order.metadata.get("exchange")
            if exchange_name and exchange_name in self.exchanges:
                self.logger.info(f"Manual routing to {exchange_name}")
                return [self._create_routed_order(order, exchange_name)]
            else:
                self.logger.warning("No valid exchange specified for manual routing, defaulting to first exchange")
                # Default to first exchange
                exchange_name = next(iter(self.exchanges.keys()))
                return [self._create_routed_order(order, exchange_name)]

        elif self.routing_mode == "best_price":
            # Choose the exchange with the best price (best bid for buy, best ask for sell)
            exchange_name = self._select_best_price_exchange(order, market_data)
            self.logger.info(f"Best price routing to {exchange_name}")
            return [self._create_routed_order(order, exchange_name)]

        else:  # "smart" mode
            # Use a combination of factors: price, liquidity, fees, latency
            exchange_name = self._select_smart_exchange(order, market_data, fees_data, latency_data)
            self.logger.info(f"Smart routing to {exchange_name}")
            return [self._create_routed_order(order, exchange_name)]

    async def _split_and_route_order(
        self,
        order: OrderEvent,
        market_data: dict[str, dict[str, Any]],
        fees_data: dict[str, dict[str, Decimal]] | None,
        latency_data: dict[str, float] | None,
    ) -> list[OrderEvent]:
        """Split a large order and route each slice to the best exchange."""
        self.logger.info(f"Splitting order {order.quantity} into slices of {self.split_size}")
        
        routed_orders = []
        remaining_quantity = order.quantity
        slice_number = 1

        while remaining_quantity > 0:
            # Determine the size of this slice
            slice_size = min(self.split_size, remaining_quantity)
            
            # Create a slice order
            slice_order = OrderEvent(
                order_id=f"{order.order_id}_slice_{slice_number}",
                symbol=order.symbol,
                timestamp=order.timestamp,
                order_type=order.order_type,
                side=order.side,
                quantity=slice_size,
                price=order.price,
                metadata={
                    **(order.metadata or {}),
                    "parent_order_id": order.order_id,
                    "slice_number": slice_number,
                    "is_slice": True
                }
            )
            
            # Route this slice
            slice_routed = await self._route_single_order(slice_order, market_data, fees_data, latency_data)
            routed_orders.extend(slice_routed)
            
            # Update remaining quantity
            remaining_quantity -= slice_size
            slice_number += 1

        self.logger.info(f"Split order into {len(routed_orders)} slices")
        return routed_orders

    def _create_routed_order(self, order: OrderEvent, exchange_name: str) -> OrderEvent:
        """Create a new OrderEvent with exchange-specific metadata."""
        return OrderEvent(
            order_id=f"{exchange_name}_{order.order_id}",
            symbol=order.symbol,
            timestamp=order.timestamp,
            order_type=order.order_type,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            metadata={
                **(order.metadata or {}),
                "exchange": exchange_name,
                "routed_at": datetime.utcnow().isoformat()
            }
        )

    def _select_best_price_exchange(
        self,
        order: OrderEvent,
        market_data: dict[str, dict[str, Any]]
    ) -> str:
        """Select the exchange with the best price for the order."""
        best_exchange = None
        best_price = None

        for exchange_name, orderbook in market_data.items():
            if exchange_name not in self.exchanges:
                continue

            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            if order.side == 'BUY':
                # For buying, we want the lowest ask (best ask)
                if asks:
                    # asks are sorted by price ascending (best ask first)
                    ask_price = Decimal(asks[0][0])  # [price, quantity]
                    if best_price is None or ask_price < best_price:
                        best_price = ask_price
                        best_exchange = exchange_name
            # For selling, we want the highest bid (best bid)
            elif bids:
                # bids are sorted by price descending (best bid first)
                bid_price = Decimal(bids[0][0])  # [price, quantity]
                if best_price is None or bid_price > best_price:
                    best_price = bid_price
                    best_exchange = exchange_name

        # If we couldn't find a valid exchange, default to the first one
        if best_exchange is None:
            best_exchange = next(iter(self.exchanges.keys()))
            self.logger.warning(f"No valid exchange found for best price, defaulting to {best_exchange}")

        return best_exchange

    def _select_smart_exchange(
        self,
        order: OrderEvent,
        market_data: dict[str, dict[str, Any]],
        fees_data: dict[str, dict[str, Decimal]] | None,
        latency_data: dict[str, float] | None,
    ) -> str:
        """
        Select the best exchange using a smart score that considers:
        - Price (primary factor)
        - Liquidity (depth at the best price)
        - Fees (maker/taker)
        - Latency
        """
        scores = {}

        for exchange_name in self.exchanges.keys():
            if exchange_name not in market_data:
                continue

            orderbook = market_data[exchange_name]
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            # Calculate base price score
            if order.side == 'BUY':
                if not asks:
                    continue  # No ask price available
                price = Decimal(asks[0][0])  # best ask
                # For buying, lower price is better, so we invert the score
                price_score = Decimal('1') / price if price > 0 else Decimal('0')
            else:  # 'SELL'
                if not bids:
                    continue  # No bid price available
                price = Decimal(bids[0][0])  # best bid
                # For selling, higher price is better
                price_score = price  # higher is better

            # Calculate liquidity score (depth at the best price)
            liquidity_score = Decimal('0')
            if order.side == 'BUY' and asks:
                # Sum the quantity at the best ask (we could sum more levels, but for simplicity just the first)
                liquidity_score = Decimal(asks[0][1])  # quantity at best ask
            elif order.side == 'SELL' and bids:
                liquidity_score = Decimal(bids[0][1])  # quantity at best bid

            # Calculate fee score (lower fees are better)
            fee_score = Decimal('1')  # default to 1 (no fee impact)
            if fees_data and exchange_name in fees_data:
                fees = fees_data[exchange_name]
                # We'll use taker fee for market orders, maker fee for limit orders as a simplification
                if order.order_type == "MARKET":
                    fee_rate = fees.get('taker', Decimal('0'))
                else:
                    fee_rate = fees.get('maker', Decimal('0'))
                # Fee score: 1 / (1 + fee_rate) so that higher fees give lower score
                if fee_rate >= 0:
                    fee_score = Decimal('1') / (Decimal('1') + fee_rate)

            # Calculate latency score (lower latency is better)
            latency_score = Decimal('1')  # default to 1 (no latency penalty)
            if latency_data and exchange_name in latency_data:
                latency = latency_data[exchange_name]
                # Latency score: 1 / (1 + latency) so that higher latency gives lower score
                # We'll scale latency to be in seconds, and assume latency < 1 second for simplicity
                # In reality, we might want to normalize latency
                latency_score = Decimal('1') / (Decimal('1') + Decimal(str(latency)))

            # Combine scores (we can weight them differently)
            # For now, we'll use equal weights and multiply the scores
            # Note: price_score is inverted for buys, so we need to adjust
            # Let's normalize each score to be roughly in the same range (0-1) and then combine
            # We'll use a weighted sum approach

            # Normalize price score: for buys, we used 1/price, for sells we used price
            # We'll convert to a score where higher is better by using a sigmoid-like transformation
            # For simplicity, we'll just use the raw scores and assume they are comparable
            # In a real system, we would normalize each factor to [0,1] range

            # Simple combination: multiply all scores (higher is better)
            combined_score = price_score * liquidity_score * fee_score * latency_score
            scores[exchange_name] = combined_score
            self.logger.debug(
                f"Exchange {exchange_name}: price={price}, price_score={price_score}, "
                f"liquidity={liquidity_score}, fee_score={fee_score}, latency_score={latency_score}, "
                f"combined={combined_score}"
            )

        # Select the exchange with the highest combined score
        if not scores:
            self.logger.warning("No valid exchanges found for smart routing, defaulting to first exchange")
            return next(iter(self.exchanges.keys()))

        best_exchange = max(scores, key=lambda x: scores[x])
        self.logger.debug(f"Selected exchange {best_exchange} with score {scores[best_exchange]}")
        return best_exchange