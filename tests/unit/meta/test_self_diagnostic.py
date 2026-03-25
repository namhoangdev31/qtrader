import polars as pl

from qtrader.meta.self_diagnostic import SelfDiagnostic

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

# Historical baseline = 2.0 Sharpe
BASELINE = 2.0

# Degradation scenario: Sharpe drops from 2.0 to 0.5
DEGRADING_PERF = pl.DataFrame(
    {
        "timestamp": list(range(20)),
        "sharpe": [2.1] * 10 + [0.5] * 10,  # 0.5 < 2.0 * 0.7 = 1.4
    }
)

# Healthy scenario: Constant 1.9 Sharpe
HEALTHY_PERF = pl.DataFrame(
    {
        "timestamp": list(range(10)),
        "sharpe": [1.9] * 10,
    }
)

# Simulation data: Peak 50k -> Drops to 40k (-10k Drawdown)
CRITICAL_PNL = pl.Series([10000, 50000, 45000, 40000])


def test_self_diagnostic_degradation_alert() -> None:
    """Verify that a drop in Sharpe correctly triggers a retraining request."""
    diagnostic = SelfDiagnostic()

    # 1. Healthy: Drop within threshold (1.9 is within 30% of 2.0)
    res_healthy = diagnostic.detect_degradation(HEALTHY_PERF, baseline_sharpe=BASELINE)
    assert res_healthy["healthy"] is True
    assert res_healthy["trigger_retrain"] is False

    # 2. Failing: Drop below (0.5 is huge drop from 2.0)
    res_failing = diagnostic.detect_degradation(DEGRADING_PERF, baseline_sharpe=BASELINE)
    assert res_failing["healthy"] is False
    assert res_failing["trigger_retrain"] is True


def test_self_diagnostic_critical_drawdown() -> None:
    """Verify detection of absolute dollar-based drawdown violations."""
    diagnostic = SelfDiagnostic()

    # Limit = -5000 USD
    # CRITICAL_PNL drop 50k -> 40k = -10k
    is_failing = diagnostic.monitor_pnl_drawdown(CRITICAL_PNL, max_drawdown_limit=-5000.0)
    assert is_failing is True

    # High tolerance = -15000 USD (Pass case)
    is_passing = diagnostic.monitor_pnl_drawdown(CRITICAL_PNL, max_drawdown_limit=-15000.0)
    assert is_passing is False


def test_self_diagnostic_empty_robustness() -> None:
    """Ensure robustness to empty metrics input."""
    diagnostic = SelfDiagnostic()
    empty_df = pl.DataFrame()
    empty_series = pl.Series()

    res = diagnostic.detect_degradation(empty_df)
    assert res["healthy"] is True

    res_pnl = diagnostic.monitor_pnl_drawdown(empty_series)
    assert res_pnl is False
