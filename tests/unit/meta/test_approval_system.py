import polars as pl
import pytest

from qtrader.meta.approval_system import ApprovalMetrics, StrategyApprovalSystem


@pytest.fixture
def committee() -> StrategyApprovalSystem:
    """Initialize StrategyApprovalSystem with industrial committee defaults."""
    return StrategyApprovalSystem(
        min_sharpe=1.5,
        max_dd=0.15,
        min_stability=1.0,  # 1/AnnualVol >= 1.0 -> Vol <= 100%
        approval_threshold=2.0,
    )


def test_approval_happy_path(committee: StrategyApprovalSystem) -> None:
    """Verify that a high-performing, stable strategy is APPROVED."""
    # S1: Sharpe 3.0, MDD 0.05, WinRate 0.6
    # Low Annual Vol (~16% -> Stability ~6.2)
    metrics = ApprovalMetrics(
        strategy_id="S1",
        sharpe=3.0,
        mdd=0.05,
        win_rate=0.6,
        turnover=20.0,
        returns=pl.Series([0.01, 0.011, 0.009, 0.012, 0.01]),
    )

    result = committee.evaluate(metrics)
    assert result["decision"] == "APPROVED"
    assert result["score"] >= 2.0


def test_approval_hard_rejection_sharpe(committee: StrategyApprovalSystem) -> None:
    """Verify that a strategy with low Sharpe is REJECTED even with low DD."""
    metrics = ApprovalMetrics(
        strategy_id="S_WEAK",
        sharpe=1.0,  # Below 1.5
        mdd=0.02,
        win_rate=0.4,
        turnover=5.0,
        returns=pl.Series([0.001, 0.0011, 0.0009]),
    )

    result = committee.evaluate(metrics)
    assert result["decision"] == "REJECTED"
    assert "SHARPE_LOW" in result["reason"]


def test_approval_hard_rejection_drawdown(committee: StrategyApprovalSystem) -> None:
    """Verify that a high-sharpe strategy with excessive drawdown is REJECTED."""
    metrics = ApprovalMetrics(
        strategy_id="S_VOLATILE",
        sharpe=2.5,
        mdd=0.25,  # Exceeds 0.15
        win_rate=0.55,
        turnover=15.0,
        returns=pl.Series([0.05, -0.10, 0.08, -0.12]),
    )

    result = committee.evaluate(metrics)
    assert result["decision"] == "REJECTED"
    assert "MDD_HIGH" in result["reason"]


def test_approval_stability_formula_comparison(committee: StrategyApprovalSystem) -> None:
    """Verify that the engine favors low-volatility (stable) strategies."""
    # S_STABLE: Very low volatility
    metrics_stable = ApprovalMetrics(
        strategy_id="S_STABLE",
        sharpe=2.0,
        mdd=0.05,
        win_rate=0.5,
        turnover=0.0,
        returns=pl.Series([0.01, 0.011, 0.009, 0.01]),
    )

    # S_JUMPY: High volatility
    metrics_jumpy = ApprovalMetrics(
        strategy_id="S_JUMPY",
        sharpe=2.0,
        mdd=0.05,
        win_rate=0.5,
        turnover=0.0,
        returns=pl.Series([0.15, -0.18, 0.22, -0.19]),
    )

    res_stable = committee.evaluate(metrics_stable)
    res_jumpy = committee.evaluate(metrics_jumpy)

    # S_STABLE should have a higher score due to higher Stability (1/AnnualVol)
    assert res_stable["score"] > res_jumpy["score"]


def test_approval_governance_report(committee: StrategyApprovalSystem) -> None:
    """Verify the validity of the committee governance report."""
    # Approve one, reject one (via gates)
    s1 = ApprovalMetrics("S1", 3.0, 0.05, 0.6, 10.0, pl.Series([0.01, 0.02, 0.015]))
    s2 = ApprovalMetrics("S2", 0.5, 0.50, 0.2, 50.0, pl.Series([0.1, -0.2, 0.05]))

    committee.evaluate(s1)
    committee.evaluate(s2)

    report = committee.get_approval_report()
    assert report["approval_rate"] == 0.5
    assert report["avg_approved_score"] > 0.0


def test_approval_insufficient_score(committee: StrategyApprovalSystem) -> None:
    """Verify that a strategy passing hard gates but having a low aggregate score is REJECTED."""
    # S_MID: Passing gates but penalised heavily by high volatility (~110% AnnVol -> Stab < 1.0)
    # Wait, 1/AnnVol < 1.0 will trigger gate.
    # We want 1/AnnVol > 1.0 (AnnVol < 100%) but overall score low.

    # AnnVol = 0.5 (50%), Stability = 2.0
    # Score = (1.0 * 1.6) + (0.5 * 2.0) + (0.5 * 0.45) - (2.0 * 0.10) - (0.3 * 100)
    # Score = 1.6 + 1.0 + 0.225 - 0.2 - 30 = -27.375

    metrics = ApprovalMetrics(
        strategy_id="S_MID",
        sharpe=1.6,
        mdd=0.10,
        win_rate=0.45,
        turnover=100.0,
        returns=pl.Series([0.05, -0.05, 0.06, -0.04]),  # Some volatility to keep it passing but mid
    )

    result = committee.evaluate(metrics)
    assert result["decision"] == "REJECTED"
    assert "INSUFFICIENT_COMPOSITE_SCORE" in result["reason"]
