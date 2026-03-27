import pytest

from qtrader.portfolio.reallocator import DynamicReallocationEngine


@pytest.fixture
def reallocator() -> DynamicReallocationEngine:
    """Initialize a DynamicReallocationEngine for institutional reallocation certification."""
    return DynamicReallocationEngine(alpha=0.5, beta=0.3, gamma=0.2)


def test_reallocator_performance_scoring_veracity(reallocator: DynamicReallocationEngine) -> None:
    """Verify that high performers gain weight relative to low performers."""
    current_weights = {"S1": 0.5, "S2": 0.5}
    metrics = {
        "S1": {"pnl": 10.0, "sharpe": 2.0, "drawdown": 0.1},
        "S2": {"pnl": 1.0, "sharpe": 0.5, "drawdown": 0.5},
    }
    # S1 Score = 0.5*10 + 0.3*2 - 0.2*0.1 = 5.0 + 0.6 - 0.02 = 5.58
    # S2 Score = 0.5*1 + 0.3*0.5 - 0.2*0.5 = 0.5 + 0.15 - 0.1 = 0.55
    # S1 Target = 5.58 / 6.13 ~ 91%

    report = reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.5)

    # Weight increased for S1, decreased for S2.
    assert report["result"] == "PASS"  # noqa: S101
    assert report["updated_distribution"]["S1"] > 0.5  # noqa: S101, PLR2004
    assert report["updated_distribution"]["S2"] < 0.5  # noqa: S101, PLR2004


def test_reallocator_strict_shift_gating(reallocator: DynamicReallocationEngine) -> None:
    """Verify that the engine enforces the 10% shift limit per cycle."""
    current_weights = {"S1": 0.5, "S2": 0.5}
    metrics = {
        "S1": {"pnl": 100.0, "sharpe": 10.0, "drawdown": 0.0},
        "S2": {"pnl": 0.0, "sharpe": 0.0, "drawdown": 10.0},
    }
    # S1 target ~ 100%. S1 delta ~ +50%. Should be capped to +10%.

    report = reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.1)

    # S1 should be ~0.6, S2 ~0.4.
    s1_w = report["updated_distribution"]["S1"]
    assert 0.59 < s1_w < 0.61  # noqa: S101, PLR2004
    assert report["metrics"]["cycle_reallocation_rate"] == pytest.approx(0.2)  # noqa: S101
    # Note: total shift (sum of |delta|) is 0.2 (0.1 from S1, -0.1 from S2).


def test_reallocator_normalization_integrity(reallocator: DynamicReallocationEngine) -> None:
    """Verify that final weights always sum to exactly 1.0."""
    current_weights = {"S1": 0.8, "S2": 0.2}
    metrics = {"S1": {"pnl": 1.0}, "S2": {"pnl": 100.0}}

    report = reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.1)

    final_weights = report["updated_distribution"]
    assert sum(final_weights.values()) == pytest.approx(1.0)  # noqa: S101


def test_reallocator_drawdown_penalty(reallocator: DynamicReallocationEngine) -> None:
    """Verify that high drawdown strategies are penalized in the scoring logic."""
    # S1 and S2 have same PnL and Sharpe, but S2 has high drawdown.
    current_weights = {"S1": 0.5, "S2": 0.5}
    metrics = {
        "S1": {"pnl": 5.0, "sharpe": 1.0, "drawdown": 0.1},
        "S2": {"pnl": 5.0, "sharpe": 1.0, "drawdown": 20.0},  # Massive DD
    }

    report = reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.5)

    # S2 score should be 0.0 (clamped). S1 score > 0.
    assert report["updated_distribution"]["S1"] > 0.5  # noqa: S101, PLR2004
    assert report["updated_distribution"]["S2"] < 0.5  # noqa: S101, PLR2004


def test_reallocator_empty_handling(reallocator: DynamicReallocationEngine) -> None:
    """Verify that empty metrics result in SKIP status."""
    report = reallocator.recalculate_allocation({}, {})

    assert report["result"] == "SKIP"  # noqa: S101
    assert report["status"] == "REALLOCATE_EMPTY"  # noqa: S101


def test_reallocator_telemetry_tracking(reallocator: DynamicReallocationEngine) -> None:
    """Verify situational awareness and cumulative capital shift telemetry."""
    current_weights = {"S1": 0.5, "S2": 0.5}
    metrics = {"S1": {"pnl": 100.0}, "S2": {"pnl": 0.0}}

    reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.1)
    reallocator.recalculate_allocation(current_weights, metrics, max_shift=0.1)

    stats = reallocator.get_reallocation_telemetry()
    assert stats["total_optimization_cycles"] == 2  # noqa: S101, PLR2004
    assert stats["cumulative_capital_shift"] == pytest.approx(0.4)  # noqa: S101
    assert stats["status"] == "REALLOCATE_GOVERNANCE"  # noqa: S101
