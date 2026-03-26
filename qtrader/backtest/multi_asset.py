from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import polars as pl

if TYPE_CHECKING:
    from qtrader.backtest.tearsheet import TearsheetGenerator

__all__ = ["PortfolioBacktest"]


@dataclass(slots=True)
class PortfolioBacktest:
    """Multi-asset portfolio backtest with rebalancing and position sizing."""

    rebalance_freq: str = "daily"
    transaction_cost_bps: float = 10.0
    initial_capital: float = 1_000_000.0
    allow_leverage: bool = False
    max_position_pct: float = 0.25

    def run(
        self,
        prices: pl.DataFrame,
        signals: pl.DataFrame,
        weights: pl.DataFrame | None = None,
    ) -> pl.DataFrame:
        """Run a portfolio backtest over wide price and signal matrices.

        Args:
            prices: Wide DataFrame with columns ``timestamp`` and one column per symbol.
            signals: Wide DataFrame with same structure as ``prices``.
            weights: Optional explicit target weights; if None, derived from signals.

        Returns:
            DataFrame with ``timestamp``, ``portfolio_return``, ``equity_curve``,
            ``drawdown`` and per-symbol contribution columns.

        Notes:
            LOOKAHEAD PREVENTION: weights are lagged by one bar before being
            multiplied by realized returns.
        """
        if "timestamp" not in prices.columns or "timestamp" not in signals.columns:
            raise ValueError("prices and signals must contain 'timestamp' column.")

        prices = prices.sort("timestamp")
        signals = signals.sort("timestamp")

        if prices.height != signals.height:
            raise ValueError("prices and signals must have the same number of rows.")

        symbol_cols = [c for c in prices.columns if c != "timestamp"]
        if not symbol_cols:
            raise ValueError("prices must contain at least one symbol column.")

        if weights is not None:
            weights = weights.sort("timestamp")
            if weights.height != prices.height:
                raise ValueError("weights must align with prices by row.")

        # Compute simple returns per symbol.
        ret_exprs = [pl.col(c).pct_change().alias(c) for c in symbol_cols]
        returns = prices.with_columns(ret_exprs)

        # Determine rebalancing key based on timestamp.
        ts = prices["timestamp"]
        if self.rebalance_freq == "daily":
            rebal_key = ts.dt.date()
        elif self.rebalance_freq == "weekly":
            rebal_key = ts.dt.week()
        elif self.rebalance_freq == "monthly":
            rebal_key = ts.dt.strftime("%Y-%m")
        else:
            raise ValueError("rebalance_freq must be 'daily', 'weekly', or 'monthly'.")

        df = pl.DataFrame({"timestamp": ts, "_rebal_key": rebal_key})
        df = df.join(signals, on="timestamp").join(returns, on="timestamp", suffix="_ret")

        # Derive target weights from explicit weights or signals.
        [f"w_{c}" for c in symbol_cols]
        if weights is not None:
            w_df = weights.rename({c: f"w_{c}" for c in symbol_cols})
            df = df.join(w_df, on="timestamp")
        else:
            # Normalize positive signals to long-only weights.
            for c in symbol_cols:
                sig_col = c
                df = df.with_columns(
                    pl.col(sig_col)
                    .clip_min(0.0)
                    .alias(f"w_{c}")
                )
            for c in symbol_cols:
                df = df.with_columns(
                    (
                        pl.col(f"w_{c}")
                        / sum(pl.col(f"w_{s}") for s in symbol_cols)
                        .over("_rebal_key")
                        .replace(0.0, None)
                        .fill_null(1.0)
                    ).alias(f"w_{c}")
                )

        # Cap max position and optionally enforce no leverage.
        for c in symbol_cols:
            df = df.with_columns(
                pl.col(f"w_{c}")
                .clip(-self.max_position_pct, self.max_position_pct)
                .alias(f"w_{c}")
            )

        if not self.allow_leverage:
            total_weight = sum(pl.col(f"w_{c}") for c in symbol_cols)
            for c in symbol_cols:
                df = df.with_columns(
                    (
                        pl.col(f"w_{c}")
                        / total_weight.replace(0.0, None).fill_null(1.0)
                    ).alias(f"w_{c}")
                )

        # LOOKAHEAD PREVENTION: lag weights by one bar before applying returns.
        for c in symbol_cols:
            df = df.with_columns(
                pl.col(f"w_{c}")
                .shift(1)
                .fill_null(0.0)
                .alias(f"w_exec_{c}")
            )

        # Compute daily portfolio return as sum_i w_exec_i * r_i.
        contrib_exprs = []
        for c in symbol_cols:
            r_col = f"{c}_ret"
            if r_col not in df.columns:
                raise ValueError(f"Missing return column '{r_col}'.")
            contrib_name = f"contrib_{c}"
            contrib_exprs.append(
                (pl.col(f"w_exec_{c}") * pl.col(r_col)).alias(contrib_name)
            )
        df = df.with_columns(contrib_exprs)

        portfolio = df.select(
            [
                "timestamp",
                sum(pl.col(f"contrib_{c}") for c in symbol_cols).alias(
                    "portfolio_return"
                ),
            ]
        )

        # Turnover and costs.
        turnover = sum(
            pl.col(f"w_exec_{c}")
            .diff()
            .abs()
            .fill_null(0.0)
            for c in symbol_cols
        )
        portfolio = portfolio.with_columns(turnover.alias("turnover"))

        cost = self.transaction_cost_bps / 10_000.0
        portfolio = portfolio.with_columns(
            (pl.col("portfolio_return") - pl.col("turnover") * cost).alias("net_return")
        )
        portfolio = portfolio.with_columns(
            (pl.col("net_return") + 1.0)
            .cum_prod()
            .mul(self.initial_capital)
            .alias("equity_curve")
        )
        portfolio = portfolio.with_columns(
            (
                pl.col("equity_curve")
                / pl.col("equity_curve").cum_max()
                - 1.0
            ).alias("drawdown")
        )

        # Attach contributions.
        contrib_cols = [f"contrib_{c}" for c in symbol_cols]
        portfolio = portfolio.join(
            df.select(["timestamp", *contrib_cols]),
            on="timestamp",
            how="left",
        )
        return portfolio

    def generate_report(self, results: pl.DataFrame, tearsheet: TearsheetGenerator) -> str:
        """Generate HTML tearsheet for portfolio backtest."""
        metrics = tearsheet.generate(results, strategy_name="portfolio")
        monthly = tearsheet.monthly_returns_table(
            results["equity_curve"], results["timestamp"]
        )
        path = tearsheet.to_html(
            metrics=metrics,
            monthly_table=monthly,
            backtest_df=results,
            output_path="/tmp/portfolio_tearsheet.html",
        )
        return path


if __name__ == "__main__":
    _ts = pl.date_range(
        low=pl.datetime(2024, 1, 1),
        high=pl.datetime(2024, 1, 10),
        interval="1d",
        eager=True,
    )
    _prices = pl.DataFrame(
        {"timestamp": _ts, "A": np.linspace(100, 110, len(_ts)), "B": np.linspace(50, 55, len(_ts))}
    )
    _signals = pl.DataFrame(
        {"timestamp": _ts, "A": np.ones(len(_ts)), "B": np.ones(len(_ts))}
    )
    _bt = PortfolioBacktest()
    _res = _bt.run(_prices, _signals)
    assert "equity_curve" in _res.columns

