import pytest

from qtrader.portfolio.scaling_governor import CapitalScalingGovernor


@pytest.fixture
def governor() -> CapitalScalingGovernor:
    """Initialize a CapitalScalingGovernor for institutional risk certification."""
    return CapitalScalingGovernor(max_scale=0.05)


def test_governor_regulated_scaling_pass(governor: CapitalScalingGovernor) -> None:
    """Verify that scale is reduced when volatility is high relative to stability."""
    # Target 5%. Stability 0.2. Vol 10.0. Ratio = 0.02. Scale = min(0.05, 0.02) = 0.02.
    metrics = {"in_drawdown": False, "vol_threshold": 15.0}
    report = governor.regulate_expansion(
        target_growth=0.05, stability_score=0.2, volatility=10.0, metrics=metrics
    )

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["regulated_scale_factor"] == 0.02  # noqa: S101, PLR2004
    assert report["metrics"]["stability_vol_efficiency"] == 0.02  # noqa: S101, PLR2004


def test_governor_drawdown_freeze(governor: CapitalScalingGovernor) -> None:
    """Verify that the scale factor is exactly 0.0 during drawdown breaching."""
    metrics = {"in_drawdown": True, "vol_threshold": 15.0}
    report = governor.regulate_expansion(
        target_growth=0.05, stability_score=1.0, volatility=1.0, metrics=metrics
    )

    assert report["result"] == "BLOCK"  # noqa: S101
    assert report["metrics"]["regulated_scale_factor"] == 0.0  # noqa: S101
    assert report["certification"]["governance_mode"] == "DRAWDOWN_FREEZE"  # noqa: S101


def test_governor_volatility_spike_reduction(governor: CapitalScalingGovernor) -> None:
    """Verify that sudden vol spikes trigger immediate scaling blocks."""
    metrics = {"in_drawdown": False, "vol_threshold": 5.0}  # Lower threshold
    report = governor.regulate_expansion(
        target_growth=0.05,
        stability_score=1.0,
        volatility=10.0,
        metrics=metrics,  # Spike
    )

    assert report["result"] == "BLOCK"  # noqa: S101
    assert report["metrics"]["regulated_scale_factor"] == 0.0  # noqa: S101
    assert report["certification"]["governance_mode"] == "VOLATILITY_THROTTLE"  # noqa: S101


def test_governor_stability_weighted_expansion(governor: CapitalScalingGovernor) -> None:
    """Verify that high stability scores allow scaling to reach the max_allowable_scale."""
    # Target 5%. Stability 10.0. Vol 1.0. Ratio = 10.0. Scale = min(0.05, 10.0) = 0.05.
    metrics = {"in_drawdown": False, "vol_threshold": 20.0}
    report = governor.regulate_expansion(
        target_growth=0.05, stability_score=10.0, volatility=1.0, metrics=metrics
    )

    assert report["metrics"]["regulated_scale_factor"] == 0.05  # noqa: S101, PLR2004


def test_governor_telemetry_tracking(governor: CapitalScalingGovernor) -> None:
    """Verify situational awareness and scaling block telemetry indexing."""
    metrics_dd = {"in_drawdown": True, "vol_threshold": 10.0}
    metrics_ok = {"in_drawdown": False, "vol_threshold": 10.0}

    governor.regulate_expansion(0.05, 1.0, 1.0, metrics_dd)  # Block
    governor.regulate_expansion(0.05, 1.0, 1.0, metrics_ok)  # Pass

    stats = governor.get_governance_telemetry()
    assert stats["total_scaling_blocks"] == 1  # noqa: S101
    assert stats["avg_regulated_expansion_rate"] == 0.025  # noqa: S101, PLR2004
    assert stats["status"] == "GOVERNANCE_HEALTH"  # noqa: S101
