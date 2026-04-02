from datetime import datetime
from unittest.mock import MagicMock

import polars as pl
import pytest

from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.backtest.integration import BacktestHarness, BacktestResult
from qtrader.backtest.tearsheet import TearsheetGenerator, TearsheetMetrics


def test_vectorized_engine_run():
    engine = VectorizedEngine()
    df = pl.DataFrame({
        "timestamp": pl.datetime_range(datetime(2023,1,1), datetime(2023,1,1,4), interval="1h", eager=True),
        "symbol": ["AAPL"] * 5,
        "close": [100.0, 101.0, 102.0, 101.5, 103.0],
        "signal": [0.1, 0.2, 0.0, -0.1, -0.2]
    })
    
    result = engine.backtest(df, signal_col="signal", initial_capital=100000.0)
    assert "equity_curve" in result.columns
    assert result.height == 5

def test_backtest_harness(monkeypatch):
    # Mock dependencies
    mock_engine = MagicMock(spec=VectorizedEngine)
    mock_tearsheet_gen = MagicMock(spec=TearsheetGenerator)
    mock_broker = MagicMock() # SimulatedBroker
    
    mock_backtest_df = pl.DataFrame({
        "timestamp": [datetime(2023,1,1)], 
        "equity_curve": [100000.0],
        "net_return": [0.0],
        "drawdown": [0.0]
    })
    mock_engine.backtest.return_value = mock_backtest_df
    
    mock_metrics = TearsheetMetrics(
        total_return=0.1, ann_return=0.12, ann_volatility=0.15,
        sharpe_ratio=0.8, sortino_ratio=1.0, calmar_ratio=0.5,
        omega_ratio=1.2, max_drawdown=-0.05, max_dd_duration_days=5,
        avg_dd_duration_days=2.0, recovery_time_days=3.0,
        total_trades=10, win_rate=0.6, avg_win_pct=0.01,
        avg_loss_pct=-0.008, profit_factor=1.5, expected_value=0.001,
        avg_turnover_daily=0.02, total_cost_pct=0.001,
        skewness=0.0, kurtosis=0.0
    )
    mock_tearsheet_gen.generate.return_value = mock_metrics
    
    harness = BacktestHarness(
        engine=mock_engine,
        tearsheet_gen=mock_tearsheet_gen,
        broker=mock_broker
    )
    
    df = pl.DataFrame({"timestamp": [datetime(2023,1,1)], "symbol": ["AAPL"], "close": [100.0], "signal": [0.1]})
    
    # run(df, signal_col, strategy_name, ...)
    result = harness.run(df, signal_col="signal", strategy_name="test_strat")
    assert result.strategy_name == "test_strat"
    assert result.tearsheet == mock_metrics
    assert "equity_curve" in result.backtest_df.columns
