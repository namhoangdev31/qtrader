from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TradeCostComponents:
    decision_price: float
    arrival_price: float
    fill_price: float
    benchmark_price: float
    quantity: float
    side: int
    timestamp: datetime
    symbol: str
    fee_rate: float = 0.0
    fee_amount: float = 0.0
    implementation_shortfall: float = 0.0
    timing_slippage: float = 0.0
    impact_slippage: float = 0.0
    fee_slippage: float = 0.0
    total_slippage: float = 0.0
    vwap_deviation: float = 0.0


@dataclass
class TCAReport:
    start_time: datetime
    end_time: datetime
    symbol: str
    total_trades: int = 0
    total_volume: float = 0.0
    total_implementation_shortfall: float = 0.0
    total_timing_slippage: float = 0.0
    total_impact_slippage: float = 0.0
    total_fee_slippage: float = 0.0
    total_slippage: float = 0.0
    total_vwap_deviation: float = 0.0
    total_fees: float = 0.0
    avg_implementation_shortfall: float = 0.0
    avg_timing_slippage: float = 0.0
    avg_impact_slippage: float = 0.0
    avg_fee_slippage: float = 0.0
    avg_slippage: float = 0.0
    avg_vwap_deviation: float = 0.0
    avg_fee_per_trade: float = 0.0
    trade_details: list[TradeCostComponents] = field(default_factory=list)

    def add_trade(self, trade: TradeCostComponents) -> None:
        self.trade_details.append(trade)
        self._update_aggregates()

    def _update_aggregates(self) -> None:
        if not self.trade_details:
            return
        self.total_trades = len(self.trade_details)
        self.total_volume = sum(abs(t.quantity) for t in self.trade_details)
        self.total_implementation_shortfall = sum(
            t.implementation_shortfall for t in self.trade_details
        )
        self.total_timing_slippage = sum(
            t.timing_slippage * abs(t.quantity) for t in self.trade_details
        )
        self.total_impact_slippage = sum(
            t.impact_slippage * abs(t.quantity) for t in self.trade_details
        )
        self.total_fee_slippage = sum(t.fee_amount for t in self.trade_details)
        self.total_vwap_deviation = sum(
            t.vwap_deviation * abs(t.quantity) for t in self.trade_details
        )
        self.total_slippage = (
            self.total_timing_slippage + self.total_impact_slippage + self.total_fee_slippage
        )
        self.total_fees = sum(t.fee_amount for t in self.trade_details)
        if self.total_trades > 0:
            self.avg_implementation_shortfall = (
                self.total_implementation_shortfall / self.total_trades
            )
            self.avg_fee_per_trade = self.total_fees / self.total_trades
        if self.total_volume > 0:
            self.avg_timing_slippage = self.total_timing_slippage / self.total_volume
            self.avg_impact_slippage = self.total_impact_slippage / self.total_volume
            self.avg_fee_slippage = self.total_fee_slippage / self.total_volume
            self.avg_slippage = self.total_slippage / self.total_volume
            self.avg_vwap_deviation = self.total_vwap_deviation / self.total_volume
        else:
            self.avg_timing_slippage = 0.0
            self.avg_impact_slippage = 0.0
            self.avg_fee_slippage = 0.0
            self.avg_slippage = 0.0
            self.avg_vwap_deviation = 0.0


def get_tca_input_schema() -> dict[str, type]:
    return {
        "timestamp": datetime,
        "symbol": str,
        "side": int,
        "quantity": float,
        "decision_price": float,
        "arrival_price": float,
        "fill_price": float,
        "benchmark_price": float,
        "fee_rate": float,
    }


def get_tca_output_schema() -> dict[str, type]:
    schema = get_tca_input_schema()
    schema.update(
        {
            "implementation_shortfall": float,
            "timing_slippage": float,
            "impact_slippage": float,
            "fee_slippage": float,
            "fee_amount": float,
            "total_slippage": float,
            "vwap_deviation": float,
        }
    )
    return schema
