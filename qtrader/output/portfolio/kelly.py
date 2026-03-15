from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["KellyCriterion"]


@dataclass(slots=True)
class KellyCriterion:
    """Optimal position sizing via Kelly formula."""

    base_vol: float = 0.2

    def single_asset_kelly(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        """Compute single-asset Kelly fraction.

        Args:
            win_rate: Probability of a winning trade in [0, 1].
            avg_win: Average win per unit of risk (positive).
            avg_loss: Average loss per unit of risk (positive).

        Returns:
            Optimal Kelly fraction ``f*`` in [0, 1] (clamped at 0 when edge is negative).
        """
        if not 0.0 <= win_rate <= 1.0:
            return 0.0
        if avg_win <= 0.0 or avg_loss <= 0.0:
            return 0.0
        loss_rate = 1.0 - win_rate
        f_star = (win_rate / avg_loss) - (loss_rate / avg_win)
        return max(0.0, float(f_star))

    def fractional_kelly(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        fraction: float = 0.25,
        regime_confidence: float = 1.0,
        max_f: float = 0.25,
    ) -> float:
        """Compute a safety-adjusted fractional Kelly fraction.

        Args:
            win_rate: Probability of a winning trade in [0, 1].
            avg_win: Average win per unit of risk (positive).
            avg_loss: Average loss per unit of risk (positive).
            fraction: Fraction of full Kelly to use (e.g. 0.25 for quarter-Kelly).
            regime_confidence: Confidence scaling factor in [0, 1].
            max_f: Hard cap on resulting fraction.

        Returns:
            Safe Kelly fraction ``f_safe`` in [0, max_f].
        """
        base = self.single_asset_kelly(win_rate, avg_win, avg_loss)
        scaled = base * max(0.0, fraction) * max(0.0, regime_confidence)
        f_safe = min(max(0.0, scaled), max_f)
        return float(f_safe)

    def portfolio_kelly(self, signals_df: pl.DataFrame) -> dict[str, float]:
        """Compute portfolio Kelly weights from per-asset signal statistics.

        Args:
            signals_df: DataFrame with columns:
                - symbol: str
                - win_rate: float in [0, 1]
                - avg_win: float > 0
                - avg_loss: float > 0
                - volatility: float > 0

        Returns:
            Dictionary mapping symbols to normalised Kelly weights summing to one.
        """
        if signals_df.height == 0:
            return {}

        df = signals_df.with_columns(
            (1.0 - pl.col("win_rate")).alias("loss_rate"),
        ).with_columns(
            (
                (pl.col("win_rate") / pl.col("avg_loss"))
                - (pl.col("loss_rate") / pl.col("avg_win"))
            ).alias("f_star"),
        )

        df = df.with_columns(
            pl.when((pl.col("volatility") > 0.0) & (pl.col("f_star") > 0.0))
            .then(pl.col("f_star") * (self.base_vol / pl.col("volatility")))
            .otherwise(0.0)
            .alias("kelly_adj"),
        )

        total = float(df["kelly_adj"].sum())
        if total <= 0.0:
            symbols = df["symbol"].to_list()
            n = len(symbols)
            if n == 0:
                return {}
            w = 1.0 / float(n)
            return {s: w for s in symbols}

        df = df.with_columns((pl.col("kelly_adj") / total).alias("weight"))

        return {
            row["symbol"]: float(row["weight"])
            for row in df.select("symbol", "weight").to_dicts()
        }


"""
Pytest-style examples (conceptual):

def test_single_asset_kelly_non_negative() -> None:
    kc = KellyCriterion()
    f = kc.single_asset_kelly(win_rate=0.6, avg_win=2.0, avg_loss=1.0)
    assert f >= 0.0


def test_fractional_kelly_capped() -> None:
    kc = KellyCriterion()
    f = kc.fractional_kelly(
        win_rate=0.6,
        avg_win=2.0,
        avg_loss=1.0,
        fraction=0.5,
        regime_confidence=1.0,
        max_f=0.25,
    )
    assert f <= 0.25


def test_portfolio_kelly_weights_sum_to_one() -> None:
    df = pl.DataFrame(
        {
            "symbol": ["A", "B"],
            "win_rate": [0.55, 0.6],
            "avg_win": [2.0, 1.5],
            "avg_loss": [1.0, 1.0],
            "volatility": [0.2, 0.25],
        },
    )
    kc = KellyCriterion()
    weights = kc.portfolio_kelly(df)
    assert abs(sum(weights.values()) - 1.0) < 1e-6
"""

