"""Slippage model for realistic trade simulation."""

import logging
import math
from decimal import Decimal
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Type alias for orderbook: {'bids': [[price, volume], ...], 'asks': [[price, volume], ...]}
Orderbook = dict[str, list[list[Any]]]


class SlippageModel:
    """
    Models market impact and slippage for order execution using a simplified Almgren-Chriss approach.

    Attributes:
        temporary_impact_factor: Factor for temporary market impact.
        permanent_impact_factor: Factor for permanent market impact.
        volatility_factor: Factor to scale volatility impact.
    """

    def __init__(
        self,
        temporary_impact_factor: Decimal = Decimal("0.1"),
        permanent_impact_factor: Decimal = Decimal("0.05"),
        volatility_factor: Decimal = Decimal("2.5"),
    ) -> None:
        self.temporary_impact = temporary_impact_factor
        self.permanent_impact = permanent_impact_factor
        self.volatility_factor = volatility_factor

    async def compute_slippage(
        self,
        symbol: str,
        side: str,  # 'BUY' or 'SELL'
        quantity: Decimal,
        orderbook: Orderbook,
        volatility: Decimal,
    ) -> Decimal:
        """
        Compute expected slippage for an order.

        Args:
            symbol: Trading symbol.
            side: Order side ('BUY' or 'SELL').
            quantity: Order quantity (positive Decimal).
            orderbook: Current orderbook state with 'bids' and 'asks' (each a list of [price, volume]).
            volatility: Recent volatility estimate (as a Decimal, e.g., 0.02 for 2%).

        Returns:
            Expected slippage in price units (positive for adverse movement).
        """
        try:
            # Calculate the mid price from the orderbook
            mid_price = self._calculate_mid_price(orderbook)
            if mid_price <= 0:
                logger.warning(f"Invalid mid price for {symbol}: {mid_price}")
                return Decimal("0")

            # Calculate the total volume available in the orderbook (we use the top level for simplicity)
            total_volume = self._calculate_total_volume(orderbook)
            if total_volume <= 0:
                # If no volume in the orderbook, we assume a very high slippage (or use a fallback)
                # For safety, we return a fixed slippage (e.g., 0.01 * mid_price) as a fallback.
                return mid_price * Decimal("0.01")

            # Participation rate: fraction of the total volume that we are trying to trade
            participation_rate = quantity / total_volume
            # Cap the participation rate at 1.0 (we cannot trade more than the available volume)
            participation_rate = min(participation_rate, Decimal("1.0"))

            # Temporary impact: linear in participation rate
            temporary = self.temporary_impact * participation_rate * mid_price

            # Permanent impact: square root of participation rate
            permanent = (
                self.permanent_impact
                * Decimal(str(math.sqrt(float(participation_rate))))
                * mid_price
            )

            # Volatility-adjusted component
            vol_component = (
                self.volatility_factor
                * volatility
                * mid_price
                * Decimal(str(math.sqrt(float(participation_rate))))
            )

            # Random component to simulate market noise (numpy seeded via SeedManager)
            random_component = Decimal(str(np.random.normal(0, float(vol_component) / 2)))

            # Total slippage (adverse to the trader)
            slippage = temporary + permanent + vol_component + abs(random_component)

            # Apply side: slippage is adverse to the trader
            if side.upper() == "SELL":
                slippage = (
                    -slippage
                )  # Selling pushes the price down (negative slippage from the trader's perspective)

            logger.debug(
                f"Slippage calculation for {symbol} {side} {quantity}: "
                f"temp={temporary:.4f}, perm={permanent:.4f}, vol={vol_component:.4f}, "
                f"rand={random_component:.4f}, total={slippage:.4f}"
            )

            return slippage
        except Exception as e:
            logger.error(f"Error computing slippage for {symbol}: {e}")
            return Decimal("0.01")  # Fallback to 10bps slippage

    def _calculate_mid_price(self, orderbook: Orderbook) -> Decimal:
        """Calculate mid price from orderbook."""
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if not bids or not asks:
            return Decimal("0")
        try:
            best_bid = Decimal(str(bids[0][0]))
            best_ask = Decimal(str(asks[0][0]))
            return (best_bid + best_ask) / Decimal("2")
        except (IndexError, ValueError, TypeError):
            return Decimal("0")

    def _calculate_total_volume(self, orderbook: Orderbook) -> Decimal:
        """Calculate the total volume in the orderbook (sum of bids and asks)."""
        try:
            bid_volume: Decimal = Decimal("0")
            for level in orderbook.get("bids", []):
                bid_volume += Decimal(str(level[1]))
            ask_volume: Decimal = Decimal("0")
            for level in orderbook.get("asks", []):
                ask_volume += Decimal(str(level[1]))
            result: Decimal = bid_volume + ask_volume
            return result
        except (IndexError, ValueError, TypeError):
            return Decimal("0")
