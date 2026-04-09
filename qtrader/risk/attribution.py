from __future__ import annotations
from dataclasses import dataclass
import polars as pl

__all__ = ["PnLAttributor"]


@dataclass(slots=True)
class PnLAttributor:
    beta: float = 1.0

    def compute(self, fills: pl.DataFrame, market_returns: pl.DataFrame) -> pl.DataFrame:
        if fills.height == 0:
            return pl.DataFrame(
                {
                    "symbol": pl.Series([], dtype=pl.String),
                    "alpha_pnl": pl.Series([], dtype=pl.Float64),
                    "beta_pnl": pl.Series([], dtype=pl.Float64),
                    "slippage_pnl": pl.Series([], dtype=pl.Float64),
                    "total_pnl": pl.Series([], dtype=pl.Float64),
                }
            )
        side_sign_expr = (
            pl.when(pl.col("side") == "BUY")
            .then(pl.lit(1.0))
            .when(pl.col("side") == "SELL")
            .then(pl.lit(-1.0))
            .otherwise(pl.lit(0.0))
        )
        fills_ext = fills.with_columns(
            side_sign_expr.alias("side_sign"),
            (pl.col("fill_price") - pl.col("arrival_price"))
            * pl.col("qty")
            * side_sign_expr.alias("slippage_pnl"),
            (pl.col("fill_price") - pl.col("arrival_price"))
            * pl.col("qty")
            * side_sign_expr.alias("realized_pnl"),
            (pl.col("arrival_price") * pl.col("qty") * side_sign_expr).alias("position_value"),
        )
        bench = (
            market_returns.group_by("symbol").agg(pl.col("return").mean().alias("benchmark_return"))
            if market_returns.height > 0
            else pl.DataFrame({"symbol": [], "benchmark_return": []})
        )
        joined = fills_ext.join(bench, on="symbol", how="left")
        joined = joined.with_columns(pl.col("benchmark_return").fill_null(0.0))
        joined = joined.with_columns(
            (pl.col("position_value") * pl.col("benchmark_return") * self.beta).alias("beta_pnl")
        )
        joined = joined.with_columns(
            (pl.col("realized_pnl") - pl.col("beta_pnl")).alias("alpha_pnl")
        )
        grouped = joined.group_by("symbol").agg(
            pl.col("alpha_pnl").sum(), pl.col("beta_pnl").sum(), pl.col("slippage_pnl").sum()
        )
        result = grouped.with_columns(
            (pl.col("alpha_pnl") + pl.col("beta_pnl") + pl.col("slippage_pnl")).alias("total_pnl")
        ).select("symbol", "alpha_pnl", "beta_pnl", "slippage_pnl", "total_pnl")
        return result
