from __future__ import annotations

import polars as pl


class MicropriceCalculator:
    """
    High-Frequency Micro-price Estimator.

    The micro-price is a fair value estimate that incorporates orderbook imbalance.
    It weightens bid and ask prices by the opposite side's volume, making it
    more sensitive to liquidity shifts than the simple mid-price.

    Conforms to the KILO.AI Industrial Grade Protocol for sub-millisecond
    vectorized computation.
    """

    @staticmethod
    def compute(
        df: pl.DataFrame,
        bid_price_col: str = "bid_price_0",
        ask_price_col: str = "ask_price_0",
        bid_vol_col: str = "bid_vol_0",
        ask_vol_col: str = "ask_vol_0",
    ) -> pl.Series:
        """
        Compute the micro-price from L1 orderbook data.

        Mathematical Model:
        P_micro = (P_ask * V_bid + P_bid * V_ask) / (V_bid + V_ask)

        Args:
            df: DataFrame containing top-level (L1) price and volume data.
            bid_price_col: Best bid price column.
            ask_price_col: Best ask price column.
            bid_vol_col: Volume at best bid.
            ask_vol_col: Volume at best ask.

        Returns:
            Polars Series of micro-price estimates (Float64).
        """
        if df.is_empty():
            return pl.Series(name="micro_price", values=[], dtype=pl.Float64)

        # Numerical stability constant
        epsilon = 1e-12

        # 1. Compute Weighted Numerator (P_ask * V_bid + P_bid * V_ask)
        numerator = (pl.col(ask_price_col) * pl.col(bid_vol_col)) + (
            pl.col(bid_price_col) * pl.col(ask_vol_col)
        )

        # 2. Compute Total Volume Denominator (V_bid + V_ask)
        denominator = pl.col(bid_vol_col) + pl.col(ask_vol_col)

        # 3. Final Calculation with zero-division safeguard
        return df.select((numerator / (denominator + epsilon)).alias("micro_price"))["micro_price"]

    @staticmethod
    def compute_mid_price(
        df: pl.DataFrame,
        bid_price_col: str = "bid_price_0",
        ask_price_col: str = "ask_price_0",
    ) -> pl.Series:
        """
        Compute the standard mid-price for comparison.

        P_mid = (P_bid + P_ask) / 2
        """
        return df.select(
            ((pl.col(bid_price_col) + pl.col(ask_price_col)) / 2.0).alias("mid_price")
        )["mid_price"]
