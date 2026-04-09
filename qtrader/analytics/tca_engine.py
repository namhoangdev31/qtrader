from dataclasses import dataclass
from datetime import datetime
import polars as pl
from qtrader.analytics.tca_models import TCAReport, TradeCostComponents, get_tca_input_schema


@dataclass
class TCAEngine:
    def __init__(self) -> None:
        self.reports: dict[str, TCAReport] = {}

    def analyze_batch(self, df: pl.DataFrame) -> pl.DataFrame:
        if "fee_rate" not in df.columns:
            df = df.with_columns(pl.lit(0.0).alias("fee_rate"))
        if "abs_qty" not in df.columns:
            df = df.with_columns(pl.col("quantity").abs().alias("abs_qty"))
        return df.with_columns(
            [
                (
                    (pl.col("fill_price") - pl.col("decision_price"))
                    * pl.col("side")
                    * pl.col("abs_qty")
                ).alias("implementation_shortfall"),
                (pl.col("arrival_price") - pl.col("decision_price")).alias("timing_slippage"),
                (pl.col("fill_price") - pl.col("arrival_price")).alias("impact_slippage"),
                (pl.col("fee_rate") * pl.col("fill_price").abs() * pl.col("abs_qty")).alias(
                    "fee_amount"
                ),
                (pl.col("fee_rate") * pl.col("fill_price").abs()).alias("fee_slippage"),
                (pl.col("fill_price") - pl.col("benchmark_price")).alias("vwap_deviation"),
            ]
        ).with_columns(
            [
                (
                    pl.col("timing_slippage") + pl.col("impact_slippage") + pl.col("fee_slippage")
                ).alias("total_slippage")
            ]
        )

    def analyze_trade(
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
        if timestamp is None:
            timestamp = datetime.now()
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
        results = self.analyze_batch(df).to_dicts()[0]
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
        return self.reports.get(symbol)

    def get_all_reports(self) -> dict[str, TCAReport]:
        return self.reports.copy()

    def clear_reports(self) -> None:
        self.reports.clear()

    def calculate_vwap_from_trades(self, prices: list[float], quantities: list[float]) -> float:
        if not prices or not quantities:
            return 0.0
        df = pl.DataFrame({"p": prices, "q": [abs(q) for q in quantities]})
        total_vol = df["q"].sum()
        if total_vol == 0:
            return 0.0
        return (df["p"] * df["q"]).sum() / total_vol
