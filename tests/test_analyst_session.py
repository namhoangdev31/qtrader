import polars as pl
import pytest

from qtrader.analyst import AnalystSession, RoleContext


# ──────────────────────────────────────────────────────────────────────────────
# Smoke
# ──────────────────────────────────────────────────────────────────────────────

def test_analyst_session_smoke() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv(symbol="AAPL", days=2)
    assert isinstance(df, pl.DataFrame)

    df = session.make_returns(df)
    df = df.with_columns(
        pl.when(pl.col("returns") > 0).then(1).otherwise(-1).alias("signal")
    )

    bt = session.run_vector_backtest(df, signal_col="signal")
    assert "equity_curve" in bt.columns

    metrics = session.performance_metrics(bt["equity_curve"])
    assert "total_return" in metrics
    assert "sharpe_ratio" in metrics


# ──────────────────────────────────────────────────────────────────────────────
# RoleContext
# ──────────────────────────────────────────────────────────────────────────────

def test_role_context_from_string() -> None:
    session = AnalystSession(role="researcher")
    assert session.role == RoleContext.RESEARCHER

def test_role_context_repr() -> None:
    s = AnalystSession(role=RoleContext.TRADER)
    assert "trader" in repr(s)

def test_info_does_not_raise() -> None:
    for role in RoleContext:
        s = AnalystSession(role=role)
        s.info()  # Should print, not raise


# ──────────────────────────────────────────────────────────────────────────────
# Rich describe
# ──────────────────────────────────────────────────────────────────────────────

def test_rich_describe() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("BTC", days=30)
    df = session.make_returns(df)
    stats = session.rich_describe(df)
    assert "columns" in stats
    first_col = list(stats["columns"].values())[0]
    assert "skew" in first_col
    assert "kurtosis" in first_col
    assert "outlier_pct (IQR)" in first_col


def test_rich_describe_table() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("BTC", days=30)
    df = session.make_returns(df)
    stats_df = session.rich_describe_table(df)
    assert isinstance(stats_df, pl.DataFrame)
    assert "column" in stats_df.columns
    assert "skew" in stats_df.columns


# ──────────────────────────────────────────────────────────────────────────────
# Rolling features
# ──────────────────────────────────────────────────────────────────────────────

def test_add_rolling_features() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("AAPL", days=60)
    df = session.make_returns(df)
    df = session.add_rolling_features(df, windows=[5, 10])
    assert "sma_5" in df.columns
    assert "sma_10" in df.columns
    assert "vol_5" in df.columns
    assert "rsi_14" in df.columns


# ──────────────────────────────────────────────────────────────────────────────
# Extended metrics
# ──────────────────────────────────────────────────────────────────────────────

def test_compute_extended_metrics() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("BTC", days=90)
    df = session.make_returns(df)
    df = df.with_columns(
        pl.when(pl.col("returns") > 0).then(1).otherwise(-1).alias("signal")
    )
    bt = session.run_vector_backtest(df, signal_col="signal")
    m = session.compute_extended_metrics(bt["equity_curve"])

    assert "sortino_ratio" in m
    assert "calmar_ratio" in m
    assert "win_rate" in m
    assert "profit_factor" in m
    assert "omega_ratio" in m
    assert 0.0 <= m["win_rate"] <= 1.0


def test_extended_metrics_from_dataframe() -> None:
    """Accepts DataFrame with equity_curve column."""
    session = AnalystSession()
    df = session.sample_ohlcv("BTC", days=60)
    df = session.make_returns(df).with_columns(
        pl.when(pl.col("returns") > 0).then(1).otherwise(-1).alias("signal")
    )
    bt = session.run_vector_backtest(df, signal_col="signal")
    # Pass DataFrame instead of Series
    m = session.compute_extended_metrics(bt.select(["equity_curve"]))
    assert "sortino_ratio" in m


# ──────────────────────────────────────────────────────────────────────────────
# Alpha score
# ──────────────────────────────────────────────────────────────────────────────

def test_run_alpha_score() -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("BTC", days=90)
    df = session.make_returns(df)
    df = session.run_alpha_score(df, forward_periods=[1, 5])
    assert "fwd_ret_1" in df.columns
    assert "fwd_ret_5" in df.columns
    assert "alpha_score" in df.columns


# ──────────────────────────────────────────────────────────────────────────────
# Export report
# ──────────────────────────────────────────────────────────────────────────────

def test_export_report(tmp_path) -> None:
    session = AnalystSession()
    df = session.sample_ohlcv("AAPL", days=30)
    df = session.make_returns(df).with_columns(
        pl.when(pl.col("returns") > 0).then(1).otherwise(-1).alias("signal")
    )
    bt = session.run_vector_backtest(df, signal_col="signal")
    metrics = session.compute_extended_metrics(bt["equity_curve"])

    out = tmp_path / "report.html"
    path = session.export_report(
        title="Test Report",
        sections={
            "Overview": "Integration test.",
            "Metrics": metrics,
            "Equity": bt["equity_curve"],
        },
        path=str(out),
    )
    assert out.exists()
    html = out.read_text()
    assert "Test Report" in html
    assert "sortino_ratio" in html


# ──────────────────────────────────────────────────────────────────────────────
# Live API – offline guard
# ──────────────────────────────────────────────────────────────────────────────

def test_ping_live_api_unreachable() -> None:
    """Should return False gracefully when no API is running."""
    session = AnalystSession()
    assert session.ping_live_api(host="localhost", port=19999) is False


def test_connect_live_api_raises_when_unreachable() -> None:
    session = AnalystSession()
    with pytest.raises(RuntimeError):  # httpx missing or connection refused
        session.connect_live_api(host="localhost", port=19999, timeout=1.0)
