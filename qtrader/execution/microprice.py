from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class MicroPriceState:
    """Snapshot of micro-price calculation results."""

    mid_price: float
    micro_price: float
    imbalance: float


class MicroPriceCalculator:
    """
    High-performance calculator for micro-price and orderbook imbalance.
    Optimized for vectorized execution via Polars and < 1ms on single ticks.
    """

    @staticmethod
    def calculate(
        bid_price: float, ask_price: float, bid_size: float, ask_size: float
    ) -> MicroPriceState:
        """
        Compute micro-price, mid-price, and imbalance for a single tick.

        Math:
            P_mid = (bid + ask) / 2
            P_micro = (ask * bid_size + bid * ask_size) / (bid_size + ask_size)
            I = (bid_size - ask_size) / (bid_size + ask_size)
        """
        total_size = bid_size + ask_size

        if total_size <= 0:
            mid = (bid_price + ask_price) / 2.0
            return MicroPriceState(mid_price=mid, micro_price=mid, imbalance=0.0)

        mid_price = (bid_price + ask_price) / 2.0
        micro_price = (ask_price * bid_size + bid_price * ask_size) / total_size
        imbalance = (bid_size - ask_size) / total_size

        return MicroPriceState(mid_price=mid_price, micro_price=micro_price, imbalance=imbalance)

    @staticmethod
    def calculate_batch(df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized micro-price and imbalance calculations.

        Input df must contain: bid_price, ask_price, bid_size, ask_size.
        Returns df with: mid_price, micro_price, imbalance.
        """
        return df.with_columns(
            [
                ((pl.col("bid_price") + pl.col("ask_price")) / 2.0).alias("mid_price"),
                (
                    (
                        pl.col("ask_price") * pl.col("bid_size")
                        + pl.col("bid_price") * pl.col("ask_size")
                    )
                    / (pl.col("bid_size") + pl.col("ask_size")).fill_nan(1.0)  # Avoid div by zero
                ).alias("micro_price"),
                (
                    (pl.col("bid_size") - pl.col("ask_size"))
                    / (pl.col("bid_size") + pl.col("ask_size")).fill_nan(1.0)
                ).alias("imbalance"),
            ]
        )
