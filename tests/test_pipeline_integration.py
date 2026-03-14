"""Lightweight tests for pipeline and backtest integration (no heavy ML)."""

from __future__ import annotations

import polars as pl

from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.backtest.integration import BacktestHarness, BacktestResult, load_baseline_metrics
from qtrader.backtest.tearsheet import TearsheetGenerator, TearsheetMetrics


def test_backtest_harness_run_returns_backtest_result() -> None:
    """BacktestHarness.run returns BacktestResult with tearsheet and backtest_df."""
    ts = pl.datetime_range(
        start=pl.datetime(2024, 1, 1),
        end=pl.datetime(2024, 2, 1),
        interval="1d",
        eager=True,
    )
    n = len(ts)
    df = pl.DataFrame({
        "timestamp": ts,
        "close": 100.0 + pl.arange(0, n, eager=True).cast(pl.Float64) * 0.1,
        "signal": [0.0] * n,
    })
    harness = BacktestHarness(
        engine=VectorizedEngine(),
        tearsheet_gen=TearsheetGenerator(),
    )
    result = harness.run(df, signal_col="signal", strategy_name="test", output_html=False)
    assert isinstance(result, BacktestResult)
    assert result.strategy_name == "test"
    assert "equity_curve" in result.backtest_df.columns
    assert result.tearsheet.sharpe_ratio is not None


def test_load_baseline_metrics_returns_none_when_missing() -> None:
    """load_baseline_metrics returns None when path does not exist."""
    assert load_baseline_metrics("/nonexistent/baseline.json") is None


def test_tearsheet_metrics_from_json_roundtrip(tmp_path: object) -> None:
    """TearsheetMetrics can be serialized to JSON and loaded back."""
    from pathlib import Path
    base = Path(str(tmp_path))
    p = base / "metrics.json"
    metrics = TearsheetMetrics(
        total_return=0.1, ann_return=0.12, ann_volatility=0.15,
        sharpe_ratio=0.8, sortino_ratio=1.0, calmar_ratio=0.5, omega_ratio=1.2,
        max_drawdown=-0.05, max_dd_duration_days=5, avg_dd_duration_days=2.0, recovery_time_days=3.0,
        total_trades=100, win_rate=0.52, avg_win_pct=0.01, avg_loss_pct=-0.008,
        profit_factor=1.1, expected_value=0.0001, avg_turnover_daily=0.02, total_cost_pct=0.001,
        skewness=0.0, kurtosis=0.0,
    )
    metrics.to_json(str(p))
    loaded = TearsheetMetrics.from_json(str(p))
    assert loaded.sharpe_ratio == metrics.sharpe_ratio
    assert loaded.win_rate == metrics.win_rate


def test_backtest_with_volume_and_borrowing_cost() -> None:
    """VectorizedEngine accepts volume_col and borrowing_cost_annual_bps."""
    ts = pl.datetime_range(
        start=pl.datetime(2024, 1, 1),
        end=pl.datetime(2024, 3, 1),
        interval="1d",
        eager=True,
    )
    n = len(ts)
    df = pl.DataFrame({
        "timestamp": ts,
        "close": 100.0 + pl.arange(0, n, eager=True).cast(pl.Float64) * 0.1,
        "volume": [1_000_000.0] * n,
        "signal": [0.0] * n,
    })
    engine = VectorizedEngine()
    out = engine.backtest(
        df,
        signal_col="signal",
        price_col="close",
        volume_col="volume",
        borrowing_cost_annual_bps=50.0,
    )
    assert "equity_curve" in out.columns
    assert "drawdown" in out.columns
    # First row can be null due to pct_change; rest should be filled
    assert out["equity_curve"].null_count() <= 1
    assert out.height == n
