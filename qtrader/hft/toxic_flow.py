from __future__ import annotations

import polars as pl


class ToxicFlowDetector:
    """
    Adverse Selection Risk Detector.

    Identifies 'toxic' order flow where prices consistently move against
    executed quotes immediately following an execution. High toxicity scores
    suggest informed trading activity, necessitating immediate quote scaling
    or spread widening to protect the Market Maker.

    Conforms to the KILO.AI Industrial Grade Protocol for zero-latency
    real-time adversarial analysis.
    """

    @staticmethod
    def compute_toxicity(
        fills: pl.DataFrame,
        market_data: pl.DataFrame,
        lookahead_steps: int = 10,
    ) -> pl.DataFrame:
        """
        Estimate toxicity scores based on post-fill fair-value drift.

        Mathematical Model:
        Toxicity_i = -Side_i * (P_future - P_fill) / P_fill

        Interpretation:
        - Side_i: +1 for Buy, -1 for Sell.
        - Positive Toxicity indicates the market moved against the execution
          (Adverse Selection).

        Args:
            fills: Execution records containing 'timestamp', 'price', and 'side'.
            market_data: L1 market snapshots containing 'timestamp' and 'mid_price'.
            lookahead_steps: Duration (in ticks) to observe for price reversion.

        Returns:
            Enriched DataFrame of executions with 'toxicity_score'.
        """
        if fills.is_empty() or market_data.is_empty():
            return fills

        # 1. Prepare future prices via temporal shifting
        # We align the future price 'lookahead_steps' into the past so join hits it
        future_prices = market_data.select(
            [
                pl.col("timestamp"),
                pl.col("mid_price").shift(-lookahead_steps).alias("future_price"),
            ]
        ).sort("timestamp")

        # 2. Synchronous Alignment using Join-Asof (Zero Latency Merging)
        enriched = fills.sort("timestamp").join_asof(
            future_prices, on="timestamp", strategy="forward"
        )

        # 3. Compute Toxicity (Adverse Selection Score)
        # We use a numerical epsilon to protect against price volatility edges
        epsilon = 1e-12
        toxicity_score = (
            -pl.col("side")
            * (pl.col("future_price") - pl.col("price"))
            / (pl.col("price") + epsilon)
        )

        # 4. Filter and Scale to [-1, 1] for signal normalization (clipping extremes)
        # Extreme toxic events (>1% drift) are capped for model stability.
        max_drift = 0.01
        return (
            enriched.with_columns(toxicity_score.alias("raw_toxicity"))
            .with_columns(
                pl.col("raw_toxicity")
                .clip(lower_bound=-max_drift, upper_bound=max_drift)
                .alias("toxicity_score")
            )
            .fill_null(0.0)
        )
