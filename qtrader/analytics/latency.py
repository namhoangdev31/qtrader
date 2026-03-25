"""Latency breakdown analysis for the 4-stage trading pipeline."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

# Hard SLA threshold: total pipeline latency must be < 100ms
_LATENCY_SLA_MS: float = 100.0


@dataclass(frozen=True)
class LatencyBreakdown:
    """
    Immutable latency breakdown for one pipeline execution.

    All values are in milliseconds.

    Args:
        l_alpha:  Market → Signal latency (alpha computation stage), ms.
        l_exec:   Signal → Order latency (routing/order placement), ms.
        l_fill:   Order → Fill latency (exchange round-trip), ms.
        l_total:  End-to-end pipeline latency (t_fill - t_market), ms.
    """

    l_alpha: float
    l_exec: float
    l_fill: float
    l_total: float

    @property
    def within_sla(self) -> bool:
        """Return True when total latency is below the 100ms SLA threshold."""
        return self.l_total < _LATENCY_SLA_MS

    @property
    def components_sum(self) -> float:
        """Sum of individual components (must equal l_total within floating-point tolerance)."""
        return self.l_alpha + self.l_exec + self.l_fill


class LatencyAnalyzer:
    """
    Compute and validate pipeline stage latencies.

    Accepts timestamps in milliseconds. All four timestamps must be
    monotonically non-decreasing (t_market ≤ t_signal ≤ t_order ≤ t_fill).
    """

    def compute(
        self,
        t_market: float,
        t_signal: float,
        t_order: float,
        t_fill: float,
    ) -> LatencyBreakdown:
        """
        Compute scalar latency breakdown for a single pipeline execution.

        Args:
            t_market: Timestamp when market data was received, ms.
            t_signal: Timestamp when alpha signal was generated, ms.
            t_order:  Timestamp when order was submitted, ms.
            t_fill:   Timestamp when fill confirmation was received, ms.

        Returns:
            LatencyBreakdown with per-stage and total latency.

        Raises:
            ValueError: If timestamps are not monotonically non-decreasing.
        """
        if not (t_market <= t_signal <= t_order <= t_fill):
            raise ValueError(
                "Timestamps must be monotonically non-decreasing: "
                f"t_market={t_market} t_signal={t_signal} "
                f"t_order={t_order} t_fill={t_fill}"
            )

        l_alpha = t_signal - t_market
        l_exec = t_order - t_signal
        l_fill = t_fill - t_order
        l_total = t_fill - t_market

        return LatencyBreakdown(
            l_alpha=l_alpha,
            l_exec=l_exec,
            l_fill=l_fill,
            l_total=l_total,
        )

    def compute_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Vectorized latency breakdown over a DataFrame of pipeline timestamps.

        Args:
            df: DataFrame with columns: t_market, t_signal, t_order, t_fill (all ms).

        Returns:
            Input DataFrame enriched with columns:
            l_alpha, l_exec, l_fill, l_total, within_sla.
        """
        required = {"t_market", "t_signal", "t_order", "t_fill"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        return df.with_columns(
            (pl.col("t_signal") - pl.col("t_market")).alias("l_alpha"),
            (pl.col("t_order")  - pl.col("t_signal")).alias("l_exec"),
            (pl.col("t_fill")   - pl.col("t_order")).alias("l_fill"),
            (pl.col("t_fill")   - pl.col("t_market")).alias("l_total"),
        ).with_columns(
            (pl.col("l_total") < _LATENCY_SLA_MS).alias("within_sla"),
        )

    def summarize_batch(self, df: pl.DataFrame) -> dict[str, float]:
        """
        Compute aggregate latency statistics over a batch of executions.

        Args:
            df: Output DataFrame from `compute_batch`, must have l_* columns.

        Returns:
            Dictionary with p50, p90, p99 percentiles for total latency,
            and sla_pass_rate as a fraction in [0, 1].
        """
        stats = df.select(
            pl.col("l_total").quantile(0.50).alias("p50"),
            pl.col("l_total").quantile(0.90).alias("p90"),
            pl.col("l_total").quantile(0.99).alias("p99"),
            pl.col("within_sla").mean().alias("sla_pass_rate"),
        ).row(0, named=True)

        return {k: float(v) for k, v in stats.items()}
