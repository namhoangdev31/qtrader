"""Execution quality analysis and reporting."""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["ExecutionQualityAnalyzer", "ExecutionReport"]


@dataclass(slots=True)
class ExecutionReport:
    """Summary report for a single execution (e.g. one strategy/symbol)."""

    symbol: str
    strategy: str
    total_qty: float
    avg_fill_price: float
    arrival_price: float
    vwap_benchmark: float
    slippage_bps: float
    implementation_shortfall: float
    fill_rate: float


class ExecutionQualityAnalyzer:
    """Analyze fill data to produce execution reports and summary statistics."""

    def analyze(
        self,
        fills: pl.DataFrame,
        strategy: str,
        arrival_price_col: str = "arrival_price",
        vwap_col: str = "vwap",
        decision_price: float | None = None,
    ) -> ExecutionReport:
        """Produce a single execution report for the given strategy and fills.

        Args:
            fills: DataFrame with columns fill_id, symbol, side, qty, fill_price,
                arrival_price, vwap, timestamp (and optionally decision_price).
            strategy: Strategy name for the report.
            arrival_price_col: Column name for arrival (mid) price at order submission.
            vwap_col: Column name for interval VWAP benchmark.
            decision_price: Price at decision time for implementation shortfall; if None, uses arrival.

        Returns:
            ExecutionReport with avg_fill_price, slippage_bps, implementation_shortfall, fill_rate.
        """
        if fills.height == 0:
            return ExecutionReport(
                symbol="",
                strategy=strategy,
                total_qty=0.0,
                avg_fill_price=0.0,
                arrival_price=0.0,
                vwap_benchmark=0.0,
                slippage_bps=0.0,
                implementation_shortfall=0.0,
                fill_rate=0.0,
            )

        total_qty = float(fills["qty"].sum())
        if total_qty == 0:
            avg_fill = 0.0
        else:
            avg_fill = float((fills["qty"] * fills["fill_price"]).sum() / total_qty)

        arr = fills.get_column(arrival_price_col)
        arrival_price = float(arr.mean()) if arr.len() > 0 else 0.0
        vwap_bench = fills.get_column(vwap_col).mean()
        vwap_benchmark = float(vwap_bench) if vwap_bench is not None else 0.0

        if arrival_price and arrival_price != 0:
            slippage_bps = (avg_fill - arrival_price) / arrival_price * 10_000.0
        else:
            slippage_bps = 0.0

        decision = decision_price if decision_price is not None else arrival_price
        implementation_shortfall = (avg_fill - decision) * total_qty if decision else 0.0

        requested = total_qty
        fill_rate = 1.0 if requested == 0 else float(fills["qty"].sum() / requested)

        symbol = str(fills["symbol"][0]) if "symbol" in fills.columns and fills.height > 0 else ""

        return ExecutionReport(
            symbol=symbol,
            strategy=strategy,
            total_qty=total_qty,
            avg_fill_price=avg_fill,
            arrival_price=arrival_price,
            vwap_benchmark=vwap_benchmark,
            slippage_bps=slippage_bps,
            implementation_shortfall=implementation_shortfall,
            fill_rate=fill_rate,
        )

    def summary_report(self, fills: pl.DataFrame) -> pl.DataFrame:
        """Group by symbol and return average slippage_bps, average IS, total_qty per symbol.

        Expects fills with columns: symbol, side, qty, fill_price, arrival_price, vwap (optional).
        """
        if fills.height == 0:
            return pl.DataFrame(
                {
                    "symbol": pl.Series([], dtype=pl.String),
                    "avg_slippage_bps": pl.Series([], dtype=pl.Float64),
                    "avg_implementation_shortfall": pl.Series([], dtype=pl.Float64),
                    "total_qty": pl.Series([], dtype=pl.Float64),
                }
            )

        total_qty = fills.group_by("symbol").agg(pl.col("qty").sum().alias("total_qty"))
        avg_fill = fills.with_columns(
            (pl.col("qty") * pl.col("fill_price")).alias("_vw")
        ).group_by("symbol").agg(
            (pl.col("_vw").sum() / pl.col("qty").sum()).alias("avg_fill_price"),
            pl.col("arrival_price").first().alias("arrival_price"),
        )
        joined = total_qty.join(avg_fill, on="symbol")
        joined = joined.with_columns(
            pl.when(pl.col("arrival_price") > 0)
            .then((pl.col("avg_fill_price") - pl.col("arrival_price")) / pl.col("arrival_price") * 10_000.0)
            .otherwise(0.0)
            .alias("avg_slippage_bps"),
            ((pl.col("avg_fill_price") - pl.col("arrival_price")) * pl.col("total_qty")).alias("avg_implementation_shortfall"),
        )
        return joined.select(
            "symbol",
            "avg_slippage_bps",
            "avg_implementation_shortfall",
            "total_qty",
        )


"""
# Pytest-style examples:
def test_analyze_empty_fills() -> None:
    a = ExecutionQualityAnalyzer()
    r = a.analyze(pl.DataFrame(), strategy="test")
    assert r.total_qty == 0.0 and r.symbol == ""

def test_summary_report_columns() -> None:
    fills = pl.DataFrame({
        "symbol": ["A", "A"], "side": ["BUY", "BUY"], "qty": [10.0, 10.0],
        "fill_price": [100.0, 101.0], "arrival_price": [100.0, 100.0], "vwap": [100.5, 100.5],
    })
    a = ExecutionQualityAnalyzer()
    df = a.summary_report(fills)
    assert "avg_slippage_bps" in df.columns and "total_qty" in df.columns
"""
