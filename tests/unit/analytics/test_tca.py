"""Unit tests for Transaction Cost Analysis engine."""

from __future__ import annotations

import pytest
import polars as pl
from datetime import datetime, timedelta
from qtrader.analytics.tca_engine import TCAEngine
from qtrader.analytics.tca_models import TradeCostComponents, TCAReport, get_tca_input_schema


def test_analyze_batch() -> None:
    """Test analyzing a batch of trades using Polars."""
    engine = TCAEngine()
    
    # Create a batch of trades
    df = pl.DataFrame({
        "timestamp": [datetime(2026, 3, 25, 10, 0, 0), datetime(2026, 3, 25, 10, 5, 0)],
        "symbol": ["AAPL", "GOOGL"],
        "side": [1, -1],  # Buy, Sell
        "quantity": [100.0, 50.0],
        "decision_price": [100.0, 100.0],
        "arrival_price": [101.0, 99.0],
        "fill_price": [102.0, 98.0],
        "benchmark_price": [101.5, 98.5],
        "fee_rate": [0.001, 0.002]
    }, schema=get_tca_input_schema())

    # Process batch
    results_df = engine.analyze_batch(df)

    # Verify AAPL (Buy)
    aapl = results_df.filter(pl.col("symbol") == "AAPL").to_dicts()[0]
    # IS = (102 - 100) * 1 * 100 = 200
    assert aapl["implementation_shortfall"] == 200.0
    # Timing = 101 - 100 = 1
    assert aapl["timing_slippage"] == 1.0
    # Impact = 102 - 101 = 1
    assert aapl["impact_slippage"] == 1.0
    # Fee = 0.001 * 102 * 100 = 10.2
    assert aapl["fee_amount"] == pytest.approx(10.2)
    # Total Slippage = 1 + 1 + 0.102 = 2.102
    assert aapl["total_slippage"] == 2.102

    # Verify GOOGL (Sell)
    googl = results_df.filter(pl.col("symbol") == "GOOGL").to_dicts()[0]
    # IS = (98 - 100) * -1 * 50 = 100
    assert googl["implementation_shortfall"] == 100.0
    # Timing = 99 - 100 = -1
    assert googl["timing_slippage"] == -1.0
    # Impact = 98 - 99 = -1
    assert googl["impact_slippage"] == -1.0
    # Fee = 0.002 * 98 * 50 = 9.8
    assert googl["fee_amount"] == pytest.approx(9.8)
    # Total Slippage = -1 + -1 + 0.196 = -1.804
    assert googl["total_slippage"] == -1.804


def test_calculate_vwap_from_trades() -> None:
    """Test TCA engine initialization."""
    engine = TCAEngine()
    assert len(engine.reports) == 0


def test_analyze_buy_trade() -> None:
    """Test analyzing a buy trade."""
    engine = TCAEngine()

    # Buy trade: decision at 100, arrive at 101, fill at 102
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=101.0,
        fill_price=102.0,
        benchmark_price=101.5,  # VWAP
        quantity=100.0,  # 100 shares
        side=1,  # Buy
        symbol="AAPL",
        timestamp=datetime(2026, 3, 25, 10, 0, 0),
        fee_rate=0.001,  # 0.1%
    )

    # Check calculated values
    # Implementation Shortfall = (fill - decision) × side × quantity
    # = (102 - 100) × 1 × 100 = 2 × 100 = 200
    assert trade.implementation_shortfall == 200.0

    # Timing = arrival - decision = 101 - 100 = 1
    assert trade.timing_slippage == 1.0

    # Impact = fill - arrival = 102 - 101 = 1
    assert trade.impact_slippage == 1.0

    # Fee = fee_rate × fill_price × |quantity| = 0.001 × 102 × 100 = 10.2
    assert trade.fee_amount == pytest.approx(10.2, rel=1e-9)
    assert trade.fee_slippage == pytest.approx(0.102, rel=1e-9)  # Fee per share

    # Total slippage = timing + impact + fee_per_share = 1 + 1 + 0.102 = 2.102
    assert trade.total_slippage == 2.102

    # VWAP deviation = fill - benchmark = 102 - 101.5 = 0.5
    assert trade.vwap_deviation == 0.5

    # Check that trade was added to report
    report = engine.get_report("AAPL")
    assert report is not None
    assert report.total_trades == 1
    assert report.total_volume == 100.0
    assert report.total_implementation_shortfall == 200.0
    assert report.total_timing_slippage == 100.0
    assert report.total_impact_slippage == 100.0
    assert report.total_fee_slippage == pytest.approx(10.2, rel=1e-9)
    assert report.total_slippage == 210.2  # 100 shares × 2.102 per share
    assert report.total_vwap_deviation == 50.0  # 100 shares × 0.5 per share
    assert report.total_fees == pytest.approx(10.2, rel=1e-9)

    # Check averages
    assert report.avg_implementation_shortfall == 200.0
    assert report.avg_timing_slippage == pytest.approx(1.0)
    assert report.avg_impact_slippage == pytest.approx(1.0)
    assert report.avg_fee_slippage == pytest.approx(0.102)
    assert report.avg_slippage == pytest.approx(2.102)
    assert report.avg_vwap_deviation == pytest.approx(0.5)
    assert report.avg_fee_per_trade == pytest.approx(10.2)


def test_analyze_sell_trade() -> None:
    """Test analyzing a sell trade."""
    engine = TCAEngine()

    # Sell trade: decision at 100, arrive at 99, fill at 98
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=99.0,
        fill_price=98.0,
        benchmark_price=98.5,
        quantity=50.0,  # 50 shares
        side=-1,  # Sell
        symbol="GOOGL",
        timestamp=datetime(2026, 3, 25, 10, 5, 0),
        fee_rate=0.002,  # 0.2%
    )

    # Check calculated values
    # Implementation Shortfall = (fill - decision) × side × quantity
    # = (98 - 100) × (-1) × 50 = (-2) × (-1) × 50 = 2 × 50 = 100
    assert trade.implementation_shortfall == 100.0

    # Timing = arrival - decision = 99 - 100 = -1
    assert trade.timing_slippage == -1.0

    # Impact = fill - arrival = 98 - 99 = -1
    assert trade.impact_slippage == -1.0

    # Fee = fee_rate × fill_price × |quantity| = 0.002 × 98 × 50 = 9.8
    assert trade.fee_amount == pytest.approx(9.8, rel=1e-9)
    assert trade.fee_slippage == pytest.approx(0.196, rel=1e-9)  # Fee per share

    # Total slippage = timing + impact + fee_per_share = -1 + (-1) + 0.196 = -1.804
    assert trade.total_slippage == -1.804

    # VWAP deviation = fill - benchmark = 98 - 98.5 = -0.5
    assert trade.vwap_deviation == -0.5

    # Check report
    report = engine.get_report("GOOGL")
    assert report is not None
    assert report.total_trades == 1
    assert report.total_volume == 50.0
    assert report.total_implementation_shortfall == 100.0
    assert report.total_timing_slippage == -50.0  # 50 shares * -1.0
    assert report.total_impact_slippage == -50.0  # 50 shares * -1.0
    assert report.total_fee_slippage == pytest.approx(9.8)
    assert report.total_slippage == pytest.approx(-90.2) # 50 * -1.804
    assert report.total_vwap_deviation == -25.0 # 50 * -0.5
    assert report.total_fees == pytest.approx(9.8)


def test_multiple_trades_same_symbol() -> None:
    """Test analyzing multiple trades for the same symbol."""
    engine = TCAEngine()

    # First trade
    trade1 = engine.analyze_trade(
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

    # Second trade
    trade2 = engine.analyze_trade(
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

    # Check report
    report = engine.get_report("MSFT")
    assert report is not None
    assert report.total_trades == 2
    assert report.total_volume == 300.0  # 100 + 200

    # Check time range
    assert report.start_time == datetime(2026, 3, 25, 10, 0, 0)
    assert report.end_time == datetime(2026, 3, 25, 10, 30, 0)

    # Check aggregated values
    # Trade 1 IS: (101-100)×1×100 = 100
    # Trade 2 IS: (101.5-101)×1×200 = 0.5×200 = 100
    # Total IS: 200
    assert report.total_implementation_shortfall == 200.0

    # Trade 1 timing: 100.5-100 = 0.5
    # Trade 2 timing: 101.2-101 = 0.2
    # Weighted avg timing: (0.5×100 + 0.2×200)/300 = (50+40)/300 = 90/300 = 0.3
    assert report.avg_timing_slippage == pytest.approx(0.3, rel=1e-9)

    # Trade 1 impact: 101-100.5 = 0.5
    # Trade 2 impact: 101.5-101.2 = 0.3
    # Weighted avg impact: (0.5×100 + 0.3×200)/300 = (50+60)/300 = 110/300 = 0.3666...
    assert abs(report.avg_impact_slippage - 110 / 300) < 1e-10

    # Check that we can get individual trade details
    assert len(report.trade_details) == 2
    assert report.trade_details[0].quantity == 100.0
    assert report.trade_details[1].quantity == 200.0


def test_zero_slippage_case() -> None:
    """Test case with zero slippage."""
    engine = TCAEngine()

    # Perfect execution: no slippage
    trade = engine.analyze_trade(
        decision_price=100.0,
        arrival_price=100.0,
        fill_price=100.0,
        benchmark_price=100.0,
        quantity=50.0,
        side=1,
        symbol="TSLA",
        timestamp=datetime(2026, 3, 25, 11, 0, 0),
        fee_rate=0.0,  # No fees
    )

    # All slippage components should be zero
    assert trade.timing_slippage == 0.0
    assert trade.impact_slippage == 0.0
    assert trade.fee_slippage == 0.0
    assert trade.total_slippage == 0.0
    assert trade.vwap_deviation == 0.0
    assert trade.fee_amount == 0.0

    # Implementation shortfall should be zero (no price change)
    assert trade.implementation_shortfall == 0.0

    report = engine.get_report("TSLA")
    assert report is not None
    assert report.total_slippage == 0.0
    assert report.total_implementation_shortfall == 0.0
    assert report.total_fees == 0.0


def test_clear_reports() -> None:
    """Test clearing reports."""
    engine = TCAEngine()

    # Add a trade
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

    # Clear reports
    engine.clear_reports()

    assert len(engine.reports) == 0
    assert engine.get_report("AMZN") is None


def test_get_all_reports() -> None:
    """Test getting all reports."""
    engine = TCAEngine()

    # Add trades for different symbols
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

    # Check that modifying the returned dict doesn't affect internal state
    all_reports["MSFT"] = TCAReport(
        start_time=datetime(2026, 3, 25, 12, 0, 0),
        end_time=datetime(2026, 3, 25, 12, 0, 0),
        symbol="MSFT",
    )
    assert len(engine.reports) == 2  # Should still be 2
    assert "MSFT" not in engine.reports


def test_calculate_vwap_from_trades() -> None:
    """Test VWAP calculation from trades."""
    engine = TCAEngine()

    # Simple case: equal quantities
    prices = [100.0, 100.0, 100.0]
    quantities = [100.0, 100.0, 100.0]
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 100.0

    # Different quantities
    prices = [100.0, 200.0]
    quantities = [100.0, 200.0]  # 2x quantity at 2x price
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    # VWAP = (100×100 + 200×200) / (100+200) = (10000 + 40000) / 300 = 50000/300 = 166.66...
    assert abs(vwap - 50000 / 300) < 1e-10

    # Edge case: zero quantities
    prices = [100.0, 200.0]
    quantities = [0.0, 0.0]
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 0.0

    # Edge case: empty lists
    prices = []
    quantities = []
    vwap = engine.calculate_vwap_from_trades(prices, quantities)
    assert vwap == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
