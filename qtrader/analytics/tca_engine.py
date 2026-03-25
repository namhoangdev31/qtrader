from dataclasses import dataclass
from datetime import datetime

import polars as pl

from qtrader.analytics.tca_models import TCAReport, TradeCostComponents, get_tca_input_schema


@dataclass
class TCAEngine:
    """
    Transaction Cost Analysis engine for measuring execution performance.

    Uses Polars for high-performance vectorized analysis.
    Supports both batch processing and real-time single trade analysis.
    """

    def __init__(self) -> None:
        """Initialize the TCA engine."""
        self.reports: dict[str, TCAReport] = {}  # symbol -> TCAReport

    def analyze_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Analyze a batch of trades using vectorized Polars expressions.

        Required columns in df:
            - decision_price: float
            - arrival_price: float
            - fill_price: float
            - benchmark_price: float
            - quantity: float (absolute value)
            - side: int (+1 for buy, -1 for sell)
            - fee_rate: float (optional, default 0.0)

        Returns:
            pl.DataFrame with additional TCA metric columns
        """
        # Ensure optional columns exist
        if "fee_rate" not in df.columns:
            df = df.with_columns(pl.lit(0.0).alias("fee_rate"))

        # We need absolute quantity for some calculations
        # if quantity is already signed in input, we extract absolute
        if "abs_qty" not in df.columns:
            df = df.with_columns(pl.col("quantity").abs().alias("abs_qty"))

        # Vectorized calculations
        return df.with_columns(
            [
                # 1. Implementation Shortfall (IS)
                # IS = (fill_price - decision_price) * side * abs_qty
                (
                    (pl.col("fill_price") - pl.col("decision_price"))
                    * pl.col("side")
                    * pl.col("abs_qty")
                ).alias("implementation_shortfall"),
                # 2. Slippage Decomposition (Per-share)
                # Timing = arrival_price - decision_price
                (pl.col("arrival_price") - pl.col("decision_price")).alias("timing_slippage"),
                # Market Impact = fill_price - arrival_price
                (pl.col("fill_price") - pl.col("arrival_price")).alias("impact_slippage"),
                # Fee amount = fee_rate * fill_price * abs_qty
                (pl.col("fee_rate") * pl.col("fill_price").abs() * pl.col("abs_qty")).alias(
                    "fee_amount"
                ),
                # Fee per share = fee_rate * fill_price
                (pl.col("fee_rate") * pl.col("fill_price").abs()).alias("fee_slippage"),
                # 3. VWAP Deviation
                (pl.col("fill_price") - pl.col("benchmark_price")).alias("vwap_deviation"),
            ]
        ).with_columns(
            [
                # Total Slippage = Timing + Impact + Fee_per_share
                (
                    pl.col("timing_slippage") + pl.col("impact_slippage") + pl.col("fee_slippage")
                ).alias("total_slippage")
            ]
        )

    def analyze_trade(  # noqa: PLR0913
        self,
        decision_price: float,
        arrival_price: float,
        fill_price: float,
        benchmark_price: float,
        quantity: float,
        side: int,
        symbol: str,
        timestamp: datetime | None = None,
        fee_rate: float = 0.0,
    ) -> TradeCostComponents:
        """
        Analyze a single trade. Real-time wrapper around analyze_batch.
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Create a single-row DataFrame
        df = pl.DataFrame(
            {
                "timestamp": [timestamp],
                "symbol": [symbol],
                "side": [side],
                "quantity": [abs(quantity)],
                "decision_price": [decision_price],
                "arrival_price": [arrival_price],
                "fill_price": [fill_price],
                "benchmark_price": [benchmark_price],
                "fee_rate": [fee_rate],
            },
            schema=get_tca_input_schema(),
        )

        # Analyze
        results = self.analyze_batch(df).to_dicts()[0]

        # Map to dataclass
        trade = TradeCostComponents(
            decision_price=decision_price,
            arrival_price=arrival_price,
            fill_price=fill_price,
            benchmark_price=benchmark_price,
            quantity=abs(quantity),
            side=side,
            timestamp=timestamp,
            symbol=symbol,
            fee_rate=fee_rate,
            fee_amount=results["fee_amount"],
            implementation_shortfall=results["implementation_shortfall"],
            timing_slippage=results["timing_slippage"],
            impact_slippage=results["impact_slippage"],
            fee_slippage=results["fee_slippage"],
            total_slippage=results["total_slippage"],
            vwap_deviation=results["vwap_deviation"],
        )

        # Update symbol reports
        if symbol not in self.reports:
            self.reports[symbol] = TCAReport(
                start_time=timestamp, end_time=timestamp, symbol=symbol
            )
        else:
            report = self.reports[symbol]
            report.start_time = min(report.start_time, timestamp)
            report.end_time = max(report.end_time, timestamp)

        self.reports[symbol].add_trade(trade)
        return trade

    def get_report(self, symbol: str) -> TCAReport | None:
        """Get TCA report for a symbol."""
        return self.reports.get(symbol)

    def get_all_reports(self) -> dict[str, TCAReport]:
        """Get all TCA reports."""
        return self.reports.copy()

    def clear_reports(self) -> None:
        """Clear all TCA reports."""
        self.reports.clear()

    def calculate_vwap_from_trades(self, prices: list[float], quantities: list[float]) -> float:
        """Calculate VWAP from a series of trades."""
        if not prices or not quantities:
            return 0.0

        # Convert to polars for efficiency
        df = pl.DataFrame({"p": prices, "q": [abs(q) for q in quantities]})

        total_vol = df["q"].sum()
        if total_vol == 0:
            return 0.0

        return float((df["p"] * df["q"]).sum()) / float(total_vol)
