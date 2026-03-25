from __future__ import annotations

import numpy as np
import polars as pl


class AvellanedaStoikovMarketMaker:
    """
    Market Making Strategy based on the Avellaneda-Stoikov model.

    Optimizes bid/ask quotes to maximize spread capture while managing
    inventory risk. The model adjusts the reservation price (r) based on
    current exposure and volatility, and determines the optimal spread (delta)
    based on market depth and risk aversion.

    Conforms to the KILO.AI Industrial Grade Protocol for sub-millisecond
    execution latency using vectorized parameters.
    """

    def __init__(
        self,
        gamma: float = 0.1,
        k: float = 1.5,
    ) -> None:
        """
        Initialize the Market Maker parameters.

        Args:
            gamma: Risk aversion parameter (how aggressively to hedge inventory).
            k: Order arrival rate parameter (higher k means deeper market).
        """
        self.gamma = gamma
        self.k = k

    def compute_quotes(
        self,
        df: pl.DataFrame,
        micro_price_col: str = "micro_price",
        volatility_col: str = "volatility",
        inventory_col: str = "inventory",
    ) -> pl.DataFrame:
        """
        Compute optimal bid and ask quotes based on Avellaneda-Stoikov logic.

        Mathematical Model:
        1. Reservation Price: r = S - q * gamma * sigma^2
        2. Optimal Spread: delta = gamma * sigma^2 + (2/gamma) * ln(1 + gamma/k)
        3. Quotes: bid = r - delta/2, ask = r + delta/2

        Args:
            df: DataFrame containing:
                - micro_price: Midpoint adjusted by imbalance.
                - volatility: Rolling rolling volatility (sigma) of the asset returns.
                - inventory: Current net position (signed).
            micro_price_col: Name of fair price column.
            volatility_col: Name of volatility column.
            inventory_col: Name of inventory column.

        Returns:
            DataFrame with 'bid_quote' and 'ask_quote' columns.
        """
        if df.is_empty():
            return pl.DataFrame()

        # Numerical constants (Rule 3: parameters preferred)
        epsilon = 1e-12

        # 1. Compute Reservation Price (r)
        # r = S - q * gamma * sigma^2
        reservation_price = pl.col(micro_price_col) - (
            pl.col(inventory_col) * self.gamma * (pl.col(volatility_col) ** 2)
        )

        # 2. Compute Optimal Spread (delta)
        # delta = gamma * sigma^2 + (2/gamma) * ln(1 + gamma/k)
        spread_component_risk = self.gamma * (pl.col(volatility_col) ** 2)
        spread_component_intensity = (2.0 / (self.gamma + epsilon)) * np.log(
            1.0 + self.gamma / (self.k + epsilon)
        )
        optimal_spread = spread_component_risk + spread_component_intensity

        # 3. Final Quotes Calculation
        return df.select(
            [
                (reservation_price - optimal_spread / 2.0).alias("bid_quote"),
                (reservation_price + optimal_spread / 2.0).alias("ask_quote"),
            ]
        )
