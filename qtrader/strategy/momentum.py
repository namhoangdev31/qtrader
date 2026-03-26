from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from qtrader.strategy.base import BaseStrategy

__all__ = ["CrossSectionalMomentum", "TimeSeriesMomentum"]


@dataclass(slots=True)
class CrossSectionalMomentum(BaseStrategy):
    """Cross-sectional momentum strategy.

    Ranks a universe by trailing return and assigns long/short signals based on
    rank. Rebalancing frequency is left to the caller.
    """

    symbols: list[str] | None = None
    lookback_months: int = 12
    skip_months: int = 1
    long_n: int = 1
    short_n: int = 0
    rebalance_freq: str = "monthly"

    def rank_signals(self, returns: pl.DataFrame) -> pl.DataFrame:
        """Rank symbols by trailing return and assign signals.

        Args:
            returns: T×N wide DataFrame of returns, columns are symbols.

        Returns:
            DataFrame with columns:
            - symbol
            - net_return
            - rank
            - signal (1 for long, -1 for short, 0 for flat)
        """
        if returns.height == 0:
            return pl.DataFrame(
                {
                    "symbol": pl.Series([], dtype=pl.String),
                    "net_return": pl.Series([], dtype=pl.Float64),
                    "rank": pl.Series([], dtype=pl.Int64),
                    "signal": pl.Series([], dtype=pl.Int64),
                },
            )

        cols = returns.columns
        df = returns
        if self.skip_months > 0:
            skip_rows = self.skip_months
            if df.height > skip_rows:
                df = df.head(df.height - skip_rows)
            else:
                df = df.slice(0, 0)

        net = df.select([pl.col(c).sum().alias(c) for c in cols])
        long_form = net.melt(variable_name="symbol", value_name="net_return")

        ranked = long_form.with_columns(
            pl.col("net_return").rank(descending=True).cast(pl.Int64).alias("rank"),
        ).sort("rank")

        n = ranked.height
        if n == 0:
            return ranked.with_columns(pl.lit(0).alias("signal"))

        long_cut = min(self.long_n, n)
        short_cut = min(self.short_n, n - long_cut) if self.short_n > 0 else 0

        ranked = ranked.with_columns(
            pl.when(pl.col("rank") <= long_cut)
            .then(1)
            .when((self.short_n > 0) & (pl.col("rank") > n - short_cut))
            .then(-1)
            .otherwise(0)
            .alias("signal"),
        )

        return ranked


@dataclass(slots=True)
class TimeSeriesMomentum(BaseStrategy):
    """Time-series momentum signal based on trend and volatility."""

    lookback: int = 60

    def compute_signal(self, df: pl.DataFrame) -> float:
        """Compute time-series momentum signal.

        Args:
            df: Price DataFrame with at least a ``\"close\"`` column.

        Returns:
            Volatility-scaled signal in [-1.0, 1.0]. Returns 0.0 when
            insufficient data or zero volatility.
        """
        if "close" not in df.columns or df.height < self.lookback:
            return 0.0

        window = df.tail(self.lookback)["close"]
        first = float(window[0])
        last = float(window[-1])
        if first <= 0.0:
            return 0.0
        trailing_ret = (last / first) - 1.0
        vol = float(window.pct_change().drop_nulls().std()) if window.len() > 1 else 0.0
        if vol <= 0.0:
            return 0.0
        raw = (1.0 if trailing_ret > 0.0 else -1.0) * (1.0 / vol)
        if raw > 1.0:
            return 1.0
        if raw < -1.0:
            return -1.0
        return float(raw)


"""
Pytest-style examples (conceptual):

def test_cross_sectional_momentum_signals() -> None:
    returns = pl.DataFrame(
        {
            "A": [0.01, 0.02, 0.0],
            "B": [-0.01, 0.0, 0.0],
        },
    )
    strat = CrossSectionalMomentum(symbol="A", long_n=1, short_n=1)
    ranked = strat.rank_signals(returns)
    assert "signal" in ranked.columns


def test_tsmom_signal_in_range() -> None:
    prices = pl.DataFrame({"close": [100.0 + i for i in range(100)]})
    strat = TimeSeriesMomentum(symbol="A", lookback=20)
    sig = strat.compute_signal(prices)
    assert -1.0 <= sig <= 1.0
"""

