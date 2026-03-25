from typing import Literal, TypedDict

import polars as pl

from .microprice import MicroPriceCalculator


class SORResult(TypedDict):
    """Execution decision results."""

    execution_decision: Literal["limit", "market"]
    target_price: float
    micro_price: float
    imbalance: float


class MicroPriceSOR:
    """
    Smart Order Router using Micro-price and Orderbook Imbalance.
    Directs execution between LIMIT and MARKET based on liquidity pressure.
    """

    def __init__(self, pressure_threshold: float = 0.6):
        """
        Args:
            pressure_threshold: Imbalance threshold to trigger aggressive (MARKET) execution.
                                0.0 (aggressive) to 1.0 (passive).
        """
        self.pressure_threshold = pressure_threshold
        self.calculator = MicroPriceCalculator()

    def get_decision(
        self,
        side: Literal["BUY", "SELL"],
        bid_price: float,
        ask_price: float,
        bid_size: float,
        ask_size: float,
    ) -> SORResult:
        """
        Calculate execution decision and target price for a single tick.

        Logic:
            - Aggressive (MARKET) if pressure is in favor of side.
            - Passive (LIMIT) otherwise or if pressure is low.
        """
        state = self.calculator.calculate(bid_price, ask_price, bid_size, ask_size)

        # Decide execution type
        decision: Literal["limit", "market"] = "limit"
        target_price = state.mid_price

        if side == "BUY":
            # If upward pressure is strong (> threshold), go MARKET
            if state.micro_price > state.mid_price and state.imbalance > self.pressure_threshold:
                decision = "market"
                target_price = ask_price
            else:
                decision = "limit"
                target_price = bid_price

        elif side == "SELL":
            # If downward pressure is strong (< -threshold), go MARKET
            if state.micro_price < state.mid_price and state.imbalance < -self.pressure_threshold:
                decision = "market"
                target_price = bid_price
            else:
                decision = "limit"
                target_price = ask_price

        return {
            "execution_decision": decision,
            "target_price": target_price,
            "micro_price": state.micro_price,
            "imbalance": state.imbalance,
        }

    def get_decision_batch(self, side: Literal["BUY", "SELL"], df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized SOR decisions for a batch of ticks.

        Input df must contain: bid_price, ask_price, bid_size, ask_size.
        """
        # 1. Compute micro-price metrics
        df = self.calculator.calculate_batch(df)

        # 2. Vectorized decision logic
        if side == "BUY":
            df = df.with_columns(
                [
                    pl.when(
                        (pl.col("micro_price") > pl.col("mid_price"))
                        & (pl.col("imbalance") > self.pressure_threshold)
                    )
                    .then(pl.lit("market"))
                    .otherwise(pl.lit("limit"))
                    .alias("execution_decision"),
                    pl.when(
                        (pl.col("micro_price") > pl.col("mid_price"))
                        & (pl.col("imbalance") > self.pressure_threshold)
                    )
                    .then(pl.col("ask_price"))
                    .otherwise(pl.col("bid_price"))
                    .alias("target_price"),
                ]
            )
        else:  # SELL
            df = df.with_columns(
                [
                    pl.when(
                        (pl.col("micro_price") < pl.col("mid_price"))
                        & (pl.col("imbalance") < -self.pressure_threshold)
                    )
                    .then(pl.lit("market"))
                    .otherwise(pl.lit("limit"))
                    .alias("execution_decision"),
                    pl.when(
                        (pl.col("micro_price") < pl.col("mid_price"))
                        & (pl.col("imbalance") < -self.pressure_threshold)
                    )
                    .then(pl.col("bid_price"))
                    .otherwise(pl.col("ask_price"))
                    .alias("target_price"),
                ]
            )

        return df
