
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["VectorizedEngine"]


@dataclass(slots=True)
class VectorizedEngine:
    """High-performance vectorized backtest engine (Polars-native).

    All methods operate on full DataFrames without an event loop and enforce
    **zero lookahead bias** via explicit signal lags.
    """

    def backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        price_col: str = "close",
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 100_000.0,
        allow_short: bool = True,
    ) -> pl.DataFrame:
        """Run a single-asset backtest with transaction costs and slippage.

        Args:
            df: Time-ordered DataFrame with at least ``timestamp`` and ``price_col``.
            signal_col: Column with trading signals (-1 short, 0 flat, 1 long).
            price_col: Price column used to compute returns.
            transaction_cost_bps: Transaction costs in basis points per unit turnover.
            slippage_bps: Additional slippage impact per unit turnover.
            initial_capital: Starting equity.
            allow_short: If False, negative signals are clipped.

        Returns:
            Input DataFrame with additional columns:
                ``_exec_signal``, ``_asset_return``, ``_gross_return``,
                ``_turnover``, ``_cost``, ``net_return``,
                ``equity_curve``, ``drawdown``.

        Notes:
            LOOKAHEAD PREVENTION: execution signal is shifted by +1 bar so that
            trades use information only from the previous bar.
        """
        if signal_col not in df.columns:
            raise ValueError(f"Signal column '{signal_col}' not found.")
        if price_col not in df.columns:
            raise ValueError(f"Price column '{price_col}' not found.")

        exec_signal = pl.col(signal_col)
        if not allow_short:
            exec_signal = pl.col(signal_col).clip_min(0.0).clip_max(1.0)

        df_out = df.with_columns(
            [
                # LOOKAHEAD PREVENTION: trade on next bar using lagged signal.
                exec_signal.shift(1).alias("_exec_signal"),
                pl.col(price_col).pct_change().alias("_asset_return"),
            ]
        )
        df_out = df_out.with_columns(
            [
                (pl.col("_exec_signal") * pl.col("_asset_return")).alias("_gross_return"),
                pl.col("_exec_signal").diff().abs().fill_null(0.0).alias("_turnover"),
            ]
        )

        total_bps = transaction_cost_bps + slippage_bps
        cost_per_unit = total_bps / 10_000.0

        df_out = df_out.with_columns(
            (pl.col("_turnover") * cost_per_unit).alias("_cost"),
        )
        df_out = df_out.with_columns(
            (pl.col("_gross_return") - pl.col("_cost")).alias("net_return"),
        )
        df_out = df_out.with_columns(
            [
                (pl.col("net_return") + 1.0).cum_prod().mul(initial_capital).alias(
                    "equity_curve"
                ),
            ]
        )
        df_out = df_out.with_columns(
            [
                (
                    pl.col("equity_curve")
                    / pl.col("equity_curve").cum_max()
                    - 1.0
                ).alias("drawdown"),
            ]
        )
        return df_out

    def multi_signal_backtest(
        self,
        df: pl.DataFrame,
        signal_cols: list[str],
        weights: list[float] | None = None,
        price_col: str = "close",
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 100_000.0,
        allow_short: bool = True,
    ) -> pl.DataFrame:
        """Backtest a weighted combination of multiple signals.

        Args:
            df: Input DataFrame.
            signal_cols: List of signal column names.
            weights: Optional weights; if None, equal-weighted.
            price_col: Price column used to compute returns.
            transaction_cost_bps: Transaction cost bps.
            slippage_bps: Slippage bps.
            initial_capital: Starting equity.
            allow_short: Whether to allow negative composite signals.

        Returns:
            Backtest result DataFrame as in :meth:`backtest`.
        """
        if not signal_cols:
            raise ValueError("signal_cols must be non-empty.")
        for col in signal_cols:
            if col not in df.columns:
                raise ValueError(f"Signal column '{col}' not found.")

        n = len(signal_cols)
        if weights is None:
            weights = [1.0 / float(n)] * n
        if len(weights) != n:
            raise ValueError("weights length must match signal_cols length.")

        composite_expr = sum(
            w * pl.col(c) for w, c in zip(weights, signal_cols, strict=True)
        )
        df_comp = df.with_columns(composite_expr.alias("_composite_signal"))
        return self.backtest(
            df=df_comp,
            signal_col="_composite_signal",
            price_col=price_col,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps=slippage_bps,
            initial_capital=initial_capital,
            allow_short=allow_short,
        )

    def cross_sectional_backtest(
        self,
        df: pl.DataFrame,
        top_n: int = 3,
        bottom_n: int = 0,
        rebalance_freq: str = "daily",
        transaction_cost_bps: float = 10.0,
    ) -> pl.DataFrame:
        """Cross-sectional (ranking) backtest over a symbol universe.

        Args:
            df: Long-form DataFrame with columns ``timestamp``, ``symbol``,
                ``close``, and ``signal``.
            top_n: Number of symbols to long at each rebalance.
            bottom_n: Number of symbols to short.
            rebalance_freq: ``\"daily\"``, ``\"weekly\"``, or ``\"monthly\"``.
            transaction_cost_bps: Transaction costs applied to turnover.

        Returns:
            DataFrame with portfolio-level returns and per-symbol contributions.

        Notes:
            LOOKAHEAD PREVENTION: weights are lagged by one bar before being
            applied to asset returns.
        """
        required = {"timestamp", "symbol", "close", "signal"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"df is missing required columns: {missing}")

        if rebalance_freq not in {"daily", "weekly", "monthly"}:
            raise ValueError("rebalance_freq must be one of 'daily', 'weekly', 'monthly'.")

        df_sorted = df.sort(["timestamp", "symbol"])
        ts = pl.col("timestamp")
        if rebalance_freq == "daily":
            rebalance_key = ts.dt.date()
        elif rebalance_freq == "weekly":
            rebalance_key = ts.dt.week()
        else:
            rebalance_key = ts.dt.strftime("%Y-%m")

        df_ranked = df_sorted.with_columns(rebalance_key.alias("_rebal_key"))
        df_ranked = df_ranked.with_columns(
            pl.col("signal")
            .rank("dense", descending=True)
            .over("_rebal_key")
            .alias("_rank_desc"),
            pl.col("signal")
            .rank("dense", descending=False)
            .over("_rebal_key")
            .alias("_rank_asc"),
        )

        # Define target weights per rebalance.
        long_mask = pl.col("_rank_desc") <= top_n
        short_mask = pl.col("_rank_asc") <= bottom_n
        df_weights = df_ranked.with_columns(
            pl.when(long_mask)
            .then(1.0)
            .when(short_mask)
            .then(-1.0)
            .otherwise(0.0)
            .alias("_raw_weight")
        )
        df_weights = df_weights.with_columns(
            (
                pl.col("_raw_weight")
                / pl.col("_raw_weight").abs().sum().over("_rebal_key").replace(
                    0.0, None
                ).fill_null(1.0)
            ).alias("weight"),
        )

        # LOOKAHEAD PREVENTION: lag weights by one bar per symbol.
        df_weights = df_weights.with_columns(
            pl.col("weight")
            .shift(1)
            .over("symbol")
            .fill_null(0.0)
            .alias("exec_weight")
        )

        df_weights = df_weights.with_columns(
            pl.col("close")
            .pct_change()
            .over("symbol")
            .alias("_asset_return")
        )

        df_weights = df_weights.with_columns(
            (pl.col("exec_weight") * pl.col("_asset_return")).alias(
                "symbol_return_contribution"
            )
        )

        portfolio = (
            df_weights.group_by("timestamp")
            .agg(
                [
                    pl.col("symbol_return_contribution")
                    .sum()
                    .alias("portfolio_return"),
                    pl.col("exec_weight").diff().abs().sum().alias("turnover"),
                ]
            )
            .sort("timestamp")
        )

        cost = transaction_cost_bps / 10_000.0
        portfolio = portfolio.with_columns(
            [
                (pl.col("portfolio_return") - pl.col("turnover") * cost).alias(
                    "net_return"
                )
            ]
        )
        portfolio = portfolio.with_columns(
            [
                (pl.col("net_return") + 1.0)
                .cum_prod()
                .alias("equity_curve"),
            ]
        )
        portfolio = portfolio.with_columns(
            [
                (
                    pl.col("equity_curve")
                    / pl.col("equity_curve").cum_max()
                    - 1.0
                ).alias("drawdown")
            ]
        )

        # Attach per-symbol contributions if needed.
        contrib = df_weights.select(
            ["timestamp", "symbol", "symbol_return_contribution"]
        )
        result = portfolio.join(contrib, on="timestamp", how="left")
        return result


if __name__ == "__main__":
    _df = pl.DataFrame(
        {
            "timestamp": pl.date_range(
                low=pl.datetime(2024, 1, 1),
                high=pl.datetime(2024, 1, 5),
                interval="1d",
                eager=True,
            ),
            "close": [100.0, 101.0, 102.0, 101.0, 103.0],
            "signal": [0.0, 1.0, 1.0, -1.0, 0.0],
        }
    )
    _engine = VectorizedEngine()
    _res = _engine.backtest(_df, signal_col="signal")
    assert "equity_curve" in _res.columns

