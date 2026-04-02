import pytest

from qtrader.meta.constraint_engine import ConstraintEngine


@pytest.fixture
def engine() -> ConstraintEngine:
    """Initialize the ConstraintEngine with default industrial thresholds."""
    return ConstraintEngine(
        max_risk_vol=0.20,
        max_mdd=0.10,
        max_leverage=2.0,
        max_turnover=5.0,
        max_complexity=10,
        max_adv_fraction=0.01,
    )


def test_constraint_engine_valid_strategy(engine: ConstraintEngine) -> None:
    """Verify that a strategy satisfying all constraints is validated."""
    metadata = {"num_parameters": 5}
    metrics = {
        "volatility": 0.15,
        "max_drawdown": 0.05,
        "avg_leverage": 1.5,
        "turnover": 2.0,
        "strategy_size": 1000.0,
        "avg_daily_volume": 1000000.0,
    }

    assert engine.validate(metadata, metrics) is True
    assert engine.rejection_count == 0


def test_constraint_engine_hard_rejection(engine: ConstraintEngine) -> None:
    """Verify that failing a single constraint results in hard rejection."""
    metadata = {"num_parameters": 5}

    # 1. High Volatility (0.25 > 0.20)
    metrics_vol = {"volatility": 0.25, "max_drawdown": 0.05, "avg_leverage": 1.0, "turnover": 1.0}
    res_vol = engine.validate(metadata, metrics_vol)
    assert res_vol is False
    assert engine.violation_counts["risk"] == 1

    # 2. High MDD (0.15 > 0.10)
    metrics_mdd = {"volatility": 0.1, "max_drawdown": 0.15, "avg_leverage": 1.0, "turnover": 1.0}
    res_mdd = engine.validate(metadata, metrics_mdd)
    assert res_mdd is False
    assert engine.violation_counts["risk"] == 2

    # 3. High Leverage (3.0 > 2.0)
    metrics_lev = {"volatility": 0.1, "max_drawdown": 0.05, "avg_leverage": 3.0, "turnover": 1.0}
    res_lev = engine.validate(metadata, metrics_lev)
    assert res_lev is False
    assert engine.violation_counts["leverage"] == 1

    # 4. High Complexity (Params = 15 > 10)
    metrics_comp = {"volatility": 0.1, "max_drawdown": 0.05, "avg_leverage": 1.0, "turnover": 1.0}
    res_complex = engine.validate({"num_parameters": 15}, metrics_comp)
    assert res_complex is False
    assert engine.violation_counts["complexity"] == 1


def test_constraint_engine_liquidity_violation(engine: ConstraintEngine) -> None:
    """Verify that strategies exceeding the ADV fraction limit are rejected."""
    metadata = {"num_parameters": 3}
    # Size = 20,000, ADV = 1,000,000 -> 0.02 > 0.01
    metrics = {
        "volatility": 0.12,
        "max_drawdown": 0.05,
        "avg_leverage": 1.0,
        "turnover": 1.0,
        "strategy_size": 20000.0,
        "avg_daily_volume": 1000000.0,
    }

    assert engine.validate(metadata, metrics) is False
    assert engine.violation_counts["liquidity"] == 1


def test_constraint_engine_missing_data_failsafe(engine: ConstraintEngine) -> None:
    """Verify that strategies with missing metrics are safely rejected."""
    # Empty metrics - should increment 'risk', 'leverage', etc. categories
    assert engine.validate({}, {}) is False
    assert engine.violation_counts["risk"] > 0


def test_constraint_engine_exception_handling(engine: ConstraintEngine) -> None:
    """Verify that unexpected exceptions lead to safe rejection."""
    # Force an exception by passing None as metadata where int expected
    metadata = None  # This will cause .get() to fail
    assert engine.validate(metadata, {}) is False  # type: ignore
    assert engine.violation_counts["missing_data"] == 1


def test_constraint_engine_observability_report(engine: ConstraintEngine) -> None:
    """Verify the validity of the governance telemetry report."""
    engine.validate({"num_parameters": 50}, {"volatility": 0.5})

    report = engine.get_observability_report()
    assert report["status"] == "FILTERING"
    assert report["total_rejections"] > 0
    assert report["violations"]["complexity"] > 0
