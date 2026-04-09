from __future__ import annotations

from dataclasses import dataclass

import polars as pl

try:
    import qtrader_core

    HAS_RUST_CORE = True
except ImportError:
    HAS_RUST_CORE = False
__all__ = ["VectorizedEngine"]
_ROLLING_VOL_WINDOW = 20
_PERIODS_PER_YEAR = 252


@dataclass(slots=True)
class VectorizedEngine:
    def backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        price_col: str = "close",
        transaction_cost_bps: float = 10.0,
        slippage_bps: float = 5.0,
        initial_capital: float = 100000.0,
        allow_short: bool = True,
        volume_col: str | None = None,
        impact_model: str = "square_root",
        borrowing_cost_annual_bps: float = 0.0,
    ) -> pl.DataFrame:
        if signal_col not in df.columns:
            raise ValueError(f"Signal column '{signal_col}' not found.")
        if price_col not in df.columns:
            raise ValueError(f"Price column '{price_col}' not found.")
        if volume_col is not None and volume_col not in df.columns:
            raise ValueError(f"Volume column '{volume_col}' not found.")
        exec_signal = pl.col(signal_col)
        if not allow_short:
            exec_signal = pl.col(signal_col).clip_min(0.0).clip_max(1.0)
        df_out = df.with_columns(
            [
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
        if volume_col is not None:
            sigma_daily = (
                pl.col(price_col).pct_change().rolling_std(_ROLLING_VOL_WINDOW).fill_null(0.0)
            )
            order_size_shares = (
                initial_capital * pl.col("_turnover") / pl.col(price_col)
            ).fill_null(0.0)
            daily_vol = pl.col(volume_col).replace(0.0, None).fill_null(10000000000.0)
            ratio = (order_size_shares / daily_vol).clip(upper_bound=1.0)
            impact_bps = (sigma_daily * ratio.sqrt()).fill_null(0.0)
            cost_per_unit = (transaction_cost_bps + impact_bps) / 10000.0
            df_out = df_out.with_columns((pl.col("_turnover") * cost_per_unit).alias("_cost"))
        else:
            total_bps = transaction_cost_bps + slippage_bps
            df_out = df_out.with_columns(
                (pl.col("_turnover") * (total_bps / 10000.0)).alias("_cost")
            )
        df_out = df_out.with_columns(
            (pl.col("_gross_return") - pl.col("_cost")).alias("net_return")
        )
        df_out = df_out.with_columns(
            (pl.col("net_return") + 1.0).cum_prod().mul(initial_capital).alias("equity_curve")
        )
        if borrowing_cost_annual_bps > 0.0:
            prev_equity = pl.col("equity_curve").shift(1).fill_null(initial_capital)
            short_notional = (
                pl.when(pl.col("_exec_signal") < 0)
                .then(prev_equity * pl.col("_exec_signal").abs())
                .otherwise(0.0)
            )
            short_cost_pct = (
                short_notional
                * (borrowing_cost_annual_bps / 10000.0 / _PERIODS_PER_YEAR)
                / prev_equity
            )
            df_out = df_out.with_columns(
                (pl.col("net_return") - short_cost_pct).alias("net_return")
            )
            df_out = df_out.with_columns(
                (pl.col("net_return") + 1.0).cum_prod().mul(initial_capital).alias("equity_curve")
            )
        df_out = df_out.with_columns(
            (pl.col("equity_curve") / pl.col("equity_curve").cum_max() - 1.0).alias("drawdown")
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
        initial_capital: float = 100000.0,
        allow_short: bool = True,
    ) -> pl.DataFrame:
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
        composite_expr = sum(w * pl.col(c) for (w, c) in zip(weights, signal_cols, strict=True))
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
            pl.col("signal").rank("dense", descending=True).over("_rebal_key").alias("_rank_desc"),
            pl.col("signal").rank("dense", descending=False).over("_rebal_key").alias("_rank_asc"),
        )
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
                / pl.col("_raw_weight")
                .abs()
                .sum()
                .over("_rebal_key")
                .replace(0.0, None)
                .fill_null(1.0)
            ).alias("weight")
        )
        df_weights = df_weights.with_columns(
            pl.col("weight").shift(1).over("symbol").fill_null(0.0).alias("exec_weight")
        )
        df_weights = df_weights.with_columns(
            pl.col("close").pct_change().over("symbol").alias("_asset_return")
        )
        df_weights = df_weights.with_columns(
            (pl.col("exec_weight") * pl.col("_asset_return")).alias("symbol_return_contribution")
        )
        portfolio = (
            df_weights.group_by("timestamp")
            .agg(
                [
                    pl.col("symbol_return_contribution").sum().alias("portfolio_return"),
                    pl.col("exec_weight").diff().abs().sum().alias("turnover"),
                ]
            )
            .sort("timestamp")
        )
        cost = transaction_cost_bps / 10000.0
        portfolio = portfolio.with_columns(
            [(pl.col("portfolio_return") - pl.col("turnover") * cost).alias("net_return")]
        )
        portfolio = portfolio.with_columns(
            [(pl.col("net_return") + 1.0).cum_prod().alias("equity_curve")]
        )
        portfolio = portfolio.with_columns(
            [(pl.col("equity_curve") / pl.col("equity_curve").cum_max() - 1.0).alias("drawdown")]
        )
        contrib = df_weights.select(["timestamp", "symbol", "symbol_return_contribution"])
        result = portfolio.join(contrib, on="timestamp", how="left")
        return result

    def run_hft_backtest(
        self,
        df: pl.DataFrame,
        signal_col: str,
        initial_capital: float = 100000.0,
        latency_ms: int = 5,
        fee_rate: float = 0.0001,
        slippage_bps: float = 2.0,
        max_position_usd: float = 50000.0,
        max_drawdown_pct: float = 0.1,
    ) -> tuple[pl.Series, float]:
        if not HAS_RUST_CORE:
            raise ImportError("run_hft_backtest requires qtrader_core (Rust) to be installed.")
        required = {"timestamp", "bid_price", "ask_price", "bid_size", "ask_size", signal_col}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"HFT backtest requires columns: {missing}")
        config = qtrader_core.SimulatorConfig(
            initial_capital=initial_capital,
            latency_ms=latency_ms,
            fee_rate=fee_rate,
            slippage_bps=slippage_bps,
            max_position_usd=max_position_usd,
            max_drawdown_pct=max_drawdown_pct,
        )
        timestamps = df["timestamp"].cast(pl.Int64).to_numpy()
        bid_prices = df["bid_price"].to_numpy()
        ask_prices = df["ask_price"].to_numpy()
        bid_sizes = df["bid_size"].to_numpy()
        ask_sizes = df["ask_size"].to_numpy()
        signals = df[signal_col].to_numpy()
        (equity_curve_arr, final_pnl) = qtrader_core.run_hft_simulation(
            config,
            "PRIMARY_ASSET",
            timestamps,
            bid_prices,
            ask_prices,
            bid_sizes,
            ask_sizes,
            signals,
        )
        return (pl.Series(name="equity_curve", values=equity_curve_arr), final_pnl)


if __name__ == "__main__":
    _df = pl.DataFrame(
        {
            "timestamp": pl.date_range(
                low=pl.datetime(2024, 1, 1), high=pl.datetime(2024, 1, 5), interval="1d", eager=True
            ),
            "close": [100.0, 101.0, 102.0, 101.0, 103.0],
            "signal": [0.0, 1.0, 1.0, -1.0, 0.0],
        }
    )
    _engine = VectorizedEngine()
    _res = _engine.backtest(_df, signal_col="signal")
    assert "equity_curve" in _res.columns
