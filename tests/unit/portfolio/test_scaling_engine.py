import pytest

from qtrader.portfolio.scaling_engine import CapitalScalingEngine


@pytest.fixture
def scaling_engine() -> CapitalScalingEngine:
    """Initialize a CapitalScalingEngine for institutional scaling certification."""
    return CapitalScalingEngine(max_growth=0.05, global_limit=1_000_000.0)


def test_scaling_engine_growth_pass(scaling_engine: CapitalScalingEngine) -> None:
    """Verify that capital increases by 5% when stability is confirmed."""
    current_cap = 100_000.0
    metrics = {"in_drawdown": False, "std_pnl": 0.05, "max_std": 0.1}

    report = scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)

    assert report["result"] == "PASS"
    assert report["metrics"]["applied_growth_rate"] == 0.05
    assert report["metrics"]["new_scaled_capital"] == 105_000.0


def test_scaling_engine_drawdown_gating(scaling_engine: CapitalScalingEngine) -> None:
    """Verify that growth is exactly 0.0 when the portfolio is in drawdown."""
    current_cap = 100_000.0
    metrics = {"in_drawdown": True, "std_pnl": 0.01, "max_std": 2.0}

    report = scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)

    assert report["metrics"]["applied_growth_rate"] == 0.0
    assert report["readiness_trace"]["rejection_reason"] == "PORTFOLIO_IN_DRAWDOWN"


def test_scaling_engine_volatility_breach_gating(scaling_engine: CapitalScalingEngine) -> None:
    """Verify that growth is suspended when PnL variance exceeds the threshold."""
    current_cap = 100_000.0
    metrics = {
        "in_drawdown": False,
        "std_pnl": 10.0,
        "max_std": 1.0,  # Breach
    }

    report = scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)

    assert report["metrics"]["applied_growth_rate"] == 0.0
    assert report["readiness_trace"]["rejection_reason"] == "VOLATILITY_ABOVE_THRESHOLD"


def test_scaling_engine_max_growth_cap_enforcement(scaling_engine: CapitalScalingEngine) -> None:
    """Verify that a 10% target growth is strictly capped at 5% per cycle."""
    current_cap = 100_000.0
    metrics = {"in_drawdown": False, "std_pnl": 0.0, "max_std": 1.0}

    report = scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.10)

    assert report["metrics"]["applied_growth_rate"] == 0.05


def test_scaling_engine_global_capacity_limit(scaling_engine: CapitalScalingEngine) -> None:
    """Verify that scaling is suspended if the global capacity limit is reached."""
    scaling_engine = CapitalScalingEngine(max_growth=0.05, global_limit=100_000.0)
    current_cap = 100_000.0
    metrics = {"in_drawdown": False, "std_pnl": 0.0, "max_std": 1.0}

    report = scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)

    assert report["metrics"]["applied_growth_rate"] == 0.0
    assert report["readiness_trace"]["rejection_reason"] == "GLOBAL_CAPACITY_LIMIT_REACHED"


def test_scaling_engine_telemetry_tracking(scaling_engine: CapitalScalingEngine) -> None:
    """Verify situational awareness and cumulative growth telemetry indexing."""
    current_cap = 100_000.0
    metrics = {"in_drawdown": False, "std_pnl": 0.0, "max_std": 1.0}

    scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)
    scaling_engine.evaluate_scaling_readiness(current_cap, metrics, target_growth=0.05)

    stats = scaling_engine.get_scaling_telemetry()
    assert stats["total_scaling_events"] == 2
    assert stats["cumulative_scaled_growth"] == pytest.approx(0.1)
    assert stats["status"] == "SCALING_GOVERNANCE"
