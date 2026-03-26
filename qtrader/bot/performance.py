"""Real-time performance tracking from fill history."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from datetime import datetime

    from qtrader.core.event import FillEvent

__all__ = ["PerformanceTracker"]

_FILLS_SCHEMA = {
    "timestamp": pl.Datetime(time_unit="us"),
    "symbol": pl.String,
    "side": pl.String,
    "qty": pl.Float64,
    "price": pl.Float64,
    "pnl": pl.Float64,
}


@dataclass(slots=True)
class PerformanceTracker:
    """Tracks fills and computes performance metrics for the bot."""

    initial_capital: float
    _fills_df: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(
            {k: pl.Series([], dtype=v) for k, v in _FILLS_SCHEMA.items()}
        ),
        init=False,
    )

    def record_fill(self, fill: FillEvent, pnl: float) -> None:
        """Append one fill and its P&L to the history.

        Args:
            fill: The fill event.
            pnl: Realized P&L for this fill.
        """
        ts: datetime = fill.timestamp
        row = pl.DataFrame(
            {
                "timestamp": [ts],
                "symbol": [fill.symbol],
                "side": [fill.side],
                "qty": [float(fill.quantity)],
                "price": [float(fill.price)],
                "pnl": [float(pnl)],
            },
            schema=_FILLS_SCHEMA,
        )
        self._fills_df = pl.concat([self._fills_df, row], how="vertical")

    @property
    def equity_curve(self) -> pl.Series:
        """Cumulative P&L plus initial capital."""
        if self._fills_df.height == 0:
            return pl.Series("equity", [self.initial_capital])
        cum = self._fills_df["pnl"].cum_sum()
        return (cum + self.initial_capital).alias("equity")

    @property
    def win_rate(self) -> float:
        """Fraction of trades with pnl > 0."""
        if self._fills_df.height == 0:
            return 0.0
        wins = self._fills_df.filter(pl.col("pnl") > 0).height
        return float(wins) / float(self._fills_df.height)

    @property
    def profit_factor(self) -> float:
        """Sum of wins / abs(sum of losses)."""
        if self._fills_df.height == 0:
            return 0.0
        gross_profit = self._fills_df.filter(pl.col("pnl") > 0)["pnl"].sum()
        gross_loss = self._fills_df.filter(pl.col("pnl") < 0)["pnl"].sum()
        denom = abs(float(gross_loss))
        if denom == 0:
            return 0.0 if float(gross_profit) == 0 else float("inf")
        return float(gross_profit) / denom

    @property
    def expected_value(self) -> float:
        """Mean P&L per trade."""
        if self._fills_df.height == 0:
            return 0.0
        return float(self._fills_df["pnl"].mean())

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe from daily returns (252 days)."""
        if self._fills_df.height < 2:
            return 0.0
        eq = self.equity_curve
        daily = eq.pct_change().drop_nulls()
        if daily.len() == 0:
            return 0.0
        mean_ret = float(daily.mean())
        std_ret = float(daily.std())
        if std_ret == 0:
            return 0.0
        return (mean_ret / std_ret) * (252**0.5)

    @property
    def sortino_ratio(self) -> float:
        """Annualized Sortino (downside deviation)."""
        if self._fills_df.height < 2:
            return 0.0
        eq = self.equity_curve
        daily = eq.pct_change().drop_nulls()
        if daily.len() == 0:
            return 0.0
        mean_ret = float(daily.mean())
        df = daily.to_frame("ret")
        downside = df.filter(pl.col("ret") < 0)
        if downside.height == 0:
            return 0.0
        std_down = float(downside["ret"].std())
        if std_down == 0:
            return 0.0
        return (mean_ret / std_down) * (252**0.5)

    @property
    def max_drawdown(self) -> float:
        """Maximum peak-to-trough drawdown (positive number)."""
        if self._fills_df.height == 0:
            return 0.0
        eq = self.equity_curve
        hwm = eq.cum_max()
        dd = (eq - hwm) / hwm
        return abs(float(dd.min()))

    @property
    def calmar_ratio(self) -> float:
        """Annualized return / max_drawdown."""
        md = self.max_drawdown
        if md == 0 or self._fills_df.height < 2:
            return 0.0
        eq = self.equity_curve
        vals = eq.to_list()
        if not vals:
            return 0.0
        e0, e1 = float(vals[0]), float(vals[-1])
        total_ret = (e1 - e0) / e0 if e0 != 0 else 0.0
        return total_ret / md

    @property
    def kelly_fraction(self) -> float:
        """Kelly-style fraction: win_rate/avg_loss - loss_rate/avg_win."""
        if self._fills_df.height == 0:
            return 0.0
        wr = self.win_rate
        lr = 1.0 - wr
        wins = self._fills_df.filter(pl.col("pnl") > 0)["pnl"]
        losses = self._fills_df.filter(pl.col("pnl") < 0)["pnl"]
        avg_win = float(wins.mean()) if wins.len() > 0 else 0.0
        avg_loss = abs(float(losses.mean())) if losses.len() > 0 else 0.0
        if avg_loss == 0 or avg_win == 0:
            return 0.0
        k = (wr / avg_loss) - (lr / avg_win)
        return max(0.0, float(k))

    def to_dict(self) -> dict[str, float]:
        """Flatten key metrics for API /metrics endpoint."""
        return {
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expected_value": self.expected_value,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "calmar_ratio": self.calmar_ratio,
            "kelly_fraction": self.kelly_fraction,
        }


"""
# Pytest-style examples:
def test_performance_tracker_win_rate() -> None:
    pt = PerformanceTracker(initial_capital=100_000.0)
    assert pt.win_rate == 0.0
    assert pt.to_dict()["win_rate"] == 0.0

def test_performance_equity_curve_empty() -> None:
    pt = PerformanceTracker(initial_capital=50_000.0)
    eq = pt.equity_curve
    assert eq.len() == 1 and eq[0] == 50_000.0
"""
