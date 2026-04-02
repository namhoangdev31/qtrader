import pytest

from qtrader.meta.shadow_enforcer import ShadowEnforcer, ShadowMetrics


@pytest.fixture
def enforcer() -> ShadowEnforcer:
    """Initialize ShadowEnforcer with industrial defaults (7 days, 10bps slippage)."""
    return ShadowEnforcer(min_duration_days=7, max_slippage_bps=10.0, min_fill_rate=0.95)


def test_shadow_happy_path(enforcer: ShadowEnforcer) -> None:
    """Verify that a strategy outperforming baseline passes shadow testing."""
    s_metrics = ShadowMetrics("S1", 1500.0, 5.0, 0.98, 0.1)
    b_metrics = ShadowMetrics("TWAP", 1000.0, 2.0, 1.0, 0.0)

    # 8 days (exceeds min 7)
    result = enforcer.evaluate(s_metrics, b_metrics, duration_days=8)
    assert result["result"] == "PASS"
    assert result["delta"] == 500.0


def test_shadow_insufficient_duration(enforcer: ShadowEnforcer) -> None:
    """Verify that a strategy with insufficient duration is REJECTED."""
    s_metrics = ShadowMetrics("S_FAST", 500.0, 2.0, 0.99, 0.05)
    b_metrics = ShadowMetrics("TWAP", 100.0, 2.0, 1.0, 0.0)

    # 3 days (less than min 7)
    result = enforcer.evaluate(s_metrics, b_metrics, duration_days=3)
    assert result["result"] == "FAIL"
    assert result["reason"] == "INSUFFICIENT_DURATION"


def test_shadow_negative_alpha(enforcer: ShadowEnforcer) -> None:
    """Verify that a strategy underperforming the baseline is REJECTED."""
    s_metrics = ShadowMetrics("S_LOSER", 800.0, 4.0, 0.97, 0.2)
    b_metrics = ShadowMetrics("TWAP", 1200.0, 2.0, 1.0, 0.0)

    result = enforcer.evaluate(s_metrics, b_metrics, duration_days=10)
    assert result["result"] == "FAIL"
    assert "NEGATIVE_ALPHA" in result["reason"]


def test_shadow_execution_rejection(enforcer: ShadowEnforcer) -> None:
    """Verify that high slippage or low fill rate leads to REJECTION."""
    # S1: High Slippage (15bps > 10bps)
    s1 = ShadowMetrics("S_SLIP", 2000.0, 15.0, 0.98, 0.1)
    # S2: Low Fill Rate (80% < 95%)
    s2 = ShadowMetrics("S_FILL", 2000.0, 5.0, 0.80, 0.1)

    b_metrics = ShadowMetrics("TWAP", 1500.0, 2.0, 1.0, 0.0)

    res1 = enforcer.evaluate(s1, b_metrics, duration_days=10)
    res2 = enforcer.evaluate(s2, b_metrics, duration_days=10)

    assert res1["result"] == "FAIL"
    assert "HIGH_SLIPPAGE" in res1["reason"]

    assert res2["result"] == "FAIL"
    assert "LOW_FILL_RATE" in res2["reason"]


def test_shadow_governance_report(enforcer: ShadowEnforcer) -> None:
    """Verify the validity of the shadow promotion telemetry report."""
    s1 = ShadowMetrics("S_PASS", 2000.0, 2.0, 1.0, 0.0)
    s2 = ShadowMetrics("S_FAIL", 500.0, 20.0, 0.5, 0.0)
    b = ShadowMetrics("TWAP", 1000.0, 2.0, 1.0, 0.0)

    enforcer.evaluate(s1, b, duration_days=10)
    enforcer.evaluate(s2, b, duration_days=10)

    report = enforcer.get_shadow_report()
    assert report["promotion_rate"] == 0.5
    assert report["avg_pnl_delta"] == 250.0
