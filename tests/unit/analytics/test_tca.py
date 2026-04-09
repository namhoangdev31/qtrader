from __future__ import annotations
from datetime import datetime, timedelta
import polars as pl
import pytest
from qtrader.analytics.tca_engine import TCAEngine
from qtrader.analytics.tca_models import TCAReport, TradeCostComponents, get_tca_input_schema


def test_analyze_batch() -> None:
    engine = TCAEngine()
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2026, 3, 25, 10, 0, 0), datetime(2026, 3, 25, 10, 5, 0)],
            "symbol": ["AAPL", "GOOGL"],
            "side": [1, -1],
            "quantity": [100.0, 50.0],
            "decision_price": [100.0, 100.0],
            "arrival_price": [101.0, 99.0],
            "fill_price": [102.0, 98.0],
            "benchmark_price": [101.5, 98.5],
            "fee_rate": [0.001, 0.002],
        },
        schema=get_tca_input_schema(),
    )
    results_df = engine.analyze_batch(df)
    aapl = results_df.filter(pl.col("symbol") == "AAPL").to_dicts()[0]
    assert aapl["implementation_shortfall"] == 200.0
    assert aapl["timing_slippage"] == 1.0
    assert aapl["impact_slippage"] == 1.0
    assert aapl["fee_amount"] == pytest.approx(10.2)
    assert aapl["total_slippage"] == 2.102
    googl = results_df.filter(pl.col("symbol") == "GOOGL").to_dicts()[0]
    assert googl["implementation_shortfall"] == 100.0
    assert googl["timing_slippage"] == -1.0
    assert googl["impact_slippage"] == -1.0
    assert googl["fee_amount"] == pytest.approx(9.8)
    assert googl["total_slippage"] == -1.804


def test_calculate_vwap_from_trades() -> None:
    engine = TCAEngine()
    assert len(engine.reports) == 0


def test_analyze_buy_trade() -> None:
    engine = TCAEngine()
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=101.0,
        fill_price=102.0,
        benchmark_price=101.5,
        quantity=100.0,
        side=1,
        symbol="AAPL",
        timestamp=datetime(2026, 3, 25, 10, 0, 0),
        fee_rate=0.001,
    )
    assert trade.implementation_shortfall == 200.0
    assert trade.timing_slippage == 1.0
    assert trade.impact_slippage == 1.0
    assert trade.fee_amount == pytest.approx(10.2, rel=1e-09)
    assert trade.fee_slippage == pytest.approx(0.102, rel=1e-09)
    assert trade.total_slippage == 2.102
    assert trade.vwap_deviation == 0.5
    report = engine.get_report("AAPL")
    assert report is not None
    assert report.total_trades == 1
    assert report.total_volume == 100.0
    assert report.total_implementation_shortfall == 200.0
    assert report.total_timing_slippage == 100.0
    assert report.total_impact_slippage == 100.0
    assert report.total_fee_slippage == pytest.approx(10.2, rel=1e-09)
    assert report.total_slippage == 210.2
    assert report.total_vwap_deviation == 50.0
    assert report.total_fees == pytest.approx(10.2, rel=1e-09)
    assert report.avg_implementation_shortfall == 200.0
    assert report.avg_timing_slippage == pytest.approx(1.0)
    assert report.avg_impact_slippage == pytest.approx(1.0)
    assert report.avg_fee_slippage == pytest.approx(0.102)
    assert report.avg_slippage == pytest.approx(2.102)
    assert report.avg_vwap_deviation == pytest.approx(0.5)
    assert report.avg_fee_per_trade == pytest.approx(10.2)


def test_analyze_sell_trade() -> None:
    engine = TCAEngine()
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=99.0,
        fill_price=98.0,
        benchmark_price=98.5,
        quantity=50.0,
        side=-1,
        symbol="GOOGL",
        timestamp=datetime(2026, 3, 25, 10, 5, 0),
        fee_rate=0.002,
    )
    assert trade.implementation_shortfall == 100.0
    assert trade.timing_slippage == -1.0
    assert trade.impact_slippage == -1.0
    assert trade.fee_amount == pytest.approx(9.8, rel=1e-09)
    assert trade.fee_slippage == pytest.approx(0.196, rel=1e-09)
    assert trade.total_slippage == -1.804
    assert trade.vwap_deviation == -0.5
    report = engine.get_report("GOOGL")
    assert report is not None
    assert report.total_trades == 1
    assert report.total_volume == 50.0
    assert report.total_implementation_shortfall == 100.0
    assert report.total_timing_slippage == -50.0
    assert report.total_impact_slippage == -50.0
    assert report.total_fee_slippage == pytest.approx(9.8)
    assert report.total_slippage == pytest.approx(-90.2)
    assert report.total_vwap_deviation == -25.0
    assert report.total_fees == pytest.approx(9.8)


def test_multiple_trades_same_symbol() -> None:
    engine = TCAEngine()
    engine.analyze_trade(
        decision_price=100.0,
        arrival_price=100.5,
        fill_price=101.0,
        benchmark_price=100.75,
        quantity=100.0,
        side=1,
        symbol="MSFT",
        timestamp=datetime(2026, 3, 25, 10, 0, 0),
        fee_rate=0.001,
    )
    engine.analyze_trade(
        decision_price=101.0,
        arrival_price=101.2,
        fill_price=101.5,
        benchmark_price=101.3,
        quantity=200.0,
        side=1,
        symbol="MSFT",
        timestamp=datetime(2026, 3, 25, 10, 30, 0),
        fee_rate=0.001,
    )
    report = engine.get_report("MSFT")
    assert report is not None
    assert report.total_trades == 2
    assert report.total_volume == 300.0
    assert report.start_time == datetime(2026, 3, 25, 10, 0, 0)
    assert report.end_time == datetime(2026, 3, 25, 10, 30, 0)
    assert report.total_implementation_shortfall == 200.0
    assert report.avg_timing_slippage == pytest.approx(0.3, rel=1e-09)
    assert abs(report.avg_impact_slippage - 110 / 300) < 1e-10
    assert len(report.trade_details) == 2
    assert report.trade_details[0].quantity == 100.0
    assert report.trade_details[1].quantity == 200.0


def test_zero_slippage_case() -> None:
    engine = TCAEngine()
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=100.0,
        fill_price=100.0,
        benchmark_price=100.0,
        quantity=50.0,
        side=1,
        symbol="TSLA",
        timestamp=datetime(2026, 3, 25, 11, 0, 0),
        fee_rate=0.0,
    )
    assert trade.timing_slippage == 0.0
    assert trade.impact_slippage == 0.0
    assert trade.fee_slippage == 0.0
    assert trade.total_slippage == 0.0
    assert trade.vwap_deviation == 0.0
    assert trade.fee_amount == 0.0
    assert trade.implementation_shortfall == 0.0
    report = engine.get_report("TSLA")
    assert report is not None
    assert report.total_slippage == 0.0
    assert report.total_implementation_shortfall == 0.0
    assert report.total_fees == 0.0


def test_clear_reports() -> None:
    engine = TCAEngine()
    engine.analyze_trade(
        decision_price=100.0,
        arrival_price=100.0,
        fill_price=101.0,
        benchmark_price=100.5,
        quantity=100.0,
        side=1,
        symbol="AMZN",
        timestamp=datetime(2026, 3, 25, 12, 0, 0),
    )
    assert len(engine.reports) == 1
    assert engine.get_report("AMZN") is not None
    engine.clear_reports()
    assert len(engine.reports) == 0
    assert engine.get_report("AMZN") is None


def test_get_all_reports() -> None:
    engine = TCAEngine()
    engine.analyze_trade(
        decision_price=100.0,
        arrival_price=100.0,
        fill_price=101.0,
        benchmark_price=100.5,
        quantity=100.0,
        side=1,
        symbol="AAPL",
        timestamp=datetime(2026, 3, 25, 12, 0, 0),
    )
    engine.analyze_trade(
        decision_price=200.0,
        arrival_price=200.0,
        fill_price=199.0,
        benchmark_price=199.5,
        quantity=50.0,
        side=-1,
        symbol="NFLX",
        timestamp=datetime(2026, 3, 25, 12, 5, 0),
    )
    all_reports = engine.get_all_reports()
    assert len(all_reports) == 2
    assert "AAPL" in all_reports
    assert "NFLX" in all_reports
    assert all_reports["AAPL"].symbol == "AAPL"
    assert all_reports["NFLX"].symbol == "NFLX"
    all_reports["MSFT"] = TCAReport(
        start_time=datetime(2026, 3, 25, 12, 0, 0),
        end_time=datetime(2026, 3, 25, 12, 0, 0),
        symbol="MSFT",
    )
    assert len(engine.reports) == 2
    assert "MSFT" not in engine.reports


def test_calculate_vwap_from_trades() -> None:
    engine = TCAEngine()
    prices = [100.0, 100.0, 100.0]
    quantities = [100.0, 100.0, 100.0]
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 100.0
    prices = [100.0, 200.0]
    quantities = [100.0, 200.0]
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert abs(vwap - 50000 / 300) < 1e-10
    prices = [100.0, 200.0]
    quantities = [0.0, 0.0]
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 0.0
    prices = []
    quantities = []
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
