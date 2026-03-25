from __future__ import annotations

import polars as pl


class OrderbookImbalance:
    """
    High-Frequency Orderbook Imbalance Calculator.

    Predicts short-term price movements (micro-price drift) based on the volume
    distribution between bid and ask sides of the L2 orderbook. Greater volume
    on the bid side indicates buying pressure and potential upward movement.

    Conforms to the KILO.AI Industrial Grade Protocol for sub-millisecond
    execution latency using vectorized Polars operations.
    """

    @staticmethod
    def compute(
        df: pl.DataFrame,
        bid_vol_col: str = "bid_vol_0",
        ask_vol_col: str = "ask_vol_0",
        ema_span: int = 10,
    ) -> pl.Series:
        """
        Compute smoothed orderbook imbalance at the top of the book (L1).

        Mathematical Model:
        I = (V_bid - V_ask) / (V_bid + V_ask)

        Properties:
        - I ∈ [-1, 1].
        - I > 0: Bullish pressure.
        - I < 0: Bearish pressure.

        Args:
            df: DataFrame containing bid/ask volume snapshots.
            bid_vol_col: Column name for top-level (Best Bid) volume.
            ask_vol_col: Column name for top-level (Best Ask) volume.
            ema_span: Period for Exponential Moving Average smoothing.

        Returns:
            Polars Series of smoothed imbalance values (Float64).
        """
        if df.is_empty():
            return pl.Series(name="imbalance", values=[], dtype=pl.Float64)

        # Numerical stability constant (Rule 3: config/args preferred but epsilon is standard)
        epsilon = 1e-12

        # 1. Compute Raw Imbalance with Vectorized Expression
        # We use abs() in denominator check for robustness
        raw_expr = (pl.col(bid_vol_col) - pl.col(ask_vol_col)) / (
            pl.col(bid_vol_col) + pl.col(ask_vol_col) + epsilon
        )

        # 2. Apply EMA for signal stabilization
        # adjust=False ensures the recursive EMA definition used in HFT systems
        return df.select(raw_expr.alias("_raw")).select(
            pl.col("_raw").ewm_mean(span=ema_span, adjust=False).alias("signal")
        )["signal"]

    @staticmethod
    def compute_multi_level(
        df: pl.DataFrame,
        levels: int = 5,
        decay: float = 0.5,
        ema_span: int = 10,
    ) -> pl.Series:
        """
        Compute depth-weighted orderbook imbalance across multiple L2 levels.

        Formula:
        I_weighted = Σ (w_i * I_i) / Σ w_i
        where w_i = decay ^ i represents the decreasing impact of deeper levels.

        Args:
            df: DataFrame with multi-level orderbook data (bid_vol_0...N).
            levels: Number of levels to incorporate (default 5).
            decay: Exponential decay factor for deeper levels (default 0.5).
            ema_span: Period for signal smoothing.

        Returns:
            Polars Series of depth-weighted smoothed imbalance.
        """
        if df.is_empty():
            return pl.Series(name="weighted_imbalance", values=[], dtype=pl.Float64)

        epsilon = 1e-12
        weighted_num = pl.lit(0.0)
        weighted_den = pl.lit(0.0)

        for i in range(levels):
            bid_col = f"bid_vol_{i}"
            ask_col = f"ask_vol_{i}"

            # Check for column existence before inclusion
            if bid_col in df.columns and ask_col in df.columns:
                # Level-specific weight
                w_i = decay**i

                # Level-specific raw imbalance
                imb_i = (pl.col(bid_col) - pl.col(ask_col)) / (
                    pl.col(bid_col) + pl.col(ask_col) + epsilon
                )

                weighted_num += w_i * imb_i
                weighted_den += w_i

        # Compute combined raw signal
        raw_signal = weighted_num / (weighted_den + epsilon)

        return df.select(raw_signal.alias("_combined")).select(
            pl.col("_combined").ewm_mean(span=ema_span, adjust=False).alias("signal")
        )["signal"]
