from __future__ import annotations

from datetime import timedelta

import polars as pl


class SpoofingDetector:
    """
    Market Surveillance & Spoofing Detector.

    Identifies patterns of price manipulation where 'fake' liquidity (large orders)
    is introduced to the book to induce market movement, only to be cancelled
    before execution as the price approaches.

    Conforms to the KILO.AI Industrial Grade Protocol for sub-millisecond
    vectorized surveillance.
    """

    @staticmethod
    def detect_spoofing(
        events: pl.DataFrame,
        large_order_vol: float = 1000.0,
        quick_cancel_ms: int = 500,
    ) -> pl.DataFrame:
        """
        Detect spoofing patterns from a stream of order events.

        Logic:
        1. Filter for NEW orders exceeding the 'large' volume threshold.
        2. Join with CANCEL events for the same order_id.
        3. Flag those where (Cancel_Time - New_Time) < quick_cancel_ms.
        4. Exclude orders that also experienced significant FILL events.

        Args:
            events: Order events with 'timestamp', 'order_id', 'type', and 'volume'.
                Expects standard HFT event types: 'NEW', 'CANCEL', 'FILL'.
            large_order_vol: Minimum volume to consider an order a 'spoof' candidate.
            quick_cancel_ms: Maximum duration between placement and cancellation.

        Returns:
            DataFrame of flagged spoofing candidates with 'order_id' and 'duration_ms'.
        """
        if events.is_empty():
            return pl.DataFrame()

        # 1. Identify Large NEW Orders
        new_orders = events.filter(
            (pl.col("type") == "NEW") & (pl.col("volume") >= large_order_vol)
        ).select(["timestamp", "order_id", "volume"])

        # 2. Identify Cancellations
        cancels = events.filter(pl.col("type") == "CANCEL").select(
            [pl.col("timestamp").alias("cancel_time"), "order_id"]
        )

        # 3. Identify Fills (to exclude genuine large trades)
        fills = events.filter(pl.col("type") == "FILL").select("order_id").unique()

        # 4. Join and Analyze duration
        potential_spoofs = new_orders.join(cancels, on="order_id", how="inner")

        # Compute duration in milliseconds
        # We handle timedelta and extract total_milliseconds
        potential_spoofs = potential_spoofs.with_columns(
            (pl.col("cancel_time") - pl.col("timestamp")).alias("duration")
        )

        # Duration thresholding
        threshold_delta = timedelta(milliseconds=quick_cancel_ms)
        spoof_flags = potential_spoofs.filter(pl.col("duration") < threshold_delta)

        # 5. Exclude those with any Fills (spoofers typically avoid execution)
        final_flags = spoof_flags.join(fills, on="order_id", how="anti")

        return final_flags.select(
            [
                "order_id",
                pl.col("volume").alias("spoof_volume"),
                (pl.col("duration").dt.total_milliseconds()).alias("duration_ms"),
            ]
        )
