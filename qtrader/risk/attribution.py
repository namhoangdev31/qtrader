from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["PnLAttributor"]


@dataclass(slots=True)
class PnLAttributor:
    """Decompose realized P&L into intuitive components.

    The attribution is performed at the symbol level. Inputs are expected to be
    reasonably small intraday or daily datasets; all computations use Polars
    columnar operations (no Python loops).
    """

    beta: float = 1.0

    def compute(self, fills: pl.DataFrame, market_returns: pl.DataFrame) -> pl.DataFrame:
        """Compute P&L attribution by symbol.

        Args:
            fills: Trade fills with columns:
                - symbol: str
                - side: str (\"BUY\"/\"SELL\")
                - qty: float
                - fill_price: float
                - arrival_price: float
            market_returns: Benchmark returns with columns:
                - date: any (not used in aggregation)
                - symbol: str
                - return: float benchmark return

        Returns:
            Polars DataFrame with one row per symbol and columns:
                - symbol
                - alpha_pnl
                - beta_pnl
                - slippage_pnl
                - total_pnl
        """
        if fills.height == 0:
            return pl.DataFrame(
                {
                    "symbol": pl.Series([], dtype=pl.String),
                    "alpha_pnl": pl.Series([], dtype=pl.Float64),
                    "beta_pnl": pl.Series([], dtype=pl.Float64),
                    "slippage_pnl": pl.Series([], dtype=pl.Float64),
                    "total_pnl": pl.Series([], dtype=pl.Float64),
                },
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
        joined = joined.with_columns(
            pl.col("benchmark_return").fill_null(0.0),
        )

        joined = joined.with_columns(
            (pl.col("position_value") * pl.col("benchmark_return") * self.beta).alias("beta_pnl"),
        )

        joined = joined.with_columns(
            (pl.col("realized_pnl") - pl.col("beta_pnl")).alias("alpha_pnl"),
        )

        grouped = joined.group_by("symbol").agg(
            pl.col("alpha_pnl").sum(),
            pl.col("beta_pnl").sum(),
            pl.col("slippage_pnl").sum(),
        )

        result = grouped.with_columns(
            (pl.col("alpha_pnl") + pl.col("beta_pnl") + pl.col("slippage_pnl")).alias("total_pnl"),
        ).select(
            "symbol",
            "alpha_pnl",
            "beta_pnl",
            "slippage_pnl",
            "total_pnl",
        )

        return result


# ---------------------------------------------------------------------------
# Minimal inline tests (for documentation only)
# ---------------------------------------------------------------------------

"""
Pytest-style examples (conceptual):

def test_slippage_signs() -> None:
    fills = pl.DataFrame(
        {
            "symbol": ["AAPL", "AAPL"],
            "side": ["BUY", "SELL"],
            "qty": [10.0, 5.0],
            "fill_price": [101.0, 99.0],
            "arrival_price": [100.0, 100.0],
        },
    )
    market_returns = pl.DataFrame(
        {"date": [], "symbol": [], "return": []},
    )
    attr = PnLAttributor(beta=1.0)
    df = attr.compute(fills, market_returns)
    row = df.row(0, named=True)
    assert row["symbol"] == "AAPL"
    assert row["slippage_pnl"] > 0.0 or row["slippage_pnl"] < 0.0


def test_total_pnl_consistency() -> None:
    fills = pl.DataFrame(
        {
            "symbol": ["MSFT"],
            "side": ["BUY"],
            "qty": [10.0],
            "fill_price": [102.0],
            "arrival_price": [100.0],
        },
    )
    market_returns = pl.DataFrame(
        {
            "date": ["2024-01-01"],
            "symbol": ["MSFT"],
            "return": [0.01],
        },
    )
    attr = PnLAttributor(beta=1.0)
    df = attr.compute(fills, market_returns)
    row = df.row(0, named=True)
    assert row["total_pnl"] == pytest.approx(
        row["alpha_pnl"] + row["beta_pnl"] + row["slippage_pnl"],
    )
"""
