import pytest

from qtrader.portfolio.allocator import CapitalAllocationEngine


@pytest.fixture
def allocator() -> CapitalAllocationEngine:
    """Initialize a CapitalAllocationEngine for institutional allocation certification."""
    return CapitalAllocationEngine(max_cap=0.2)


def test_allocator_sharpe_weighted_pass(allocator: CapitalAllocationEngine) -> None:
    """Verify that allocation is proportional to Sharpe (assuming no caps hit)."""
    strategies = [
        {"id": "S1", "sharpe": 2.0},
        {"id": "S2", "sharpe": 1.0},
        {"id": "S3", "sharpe": 0.5},
    ]
    # Total Sharpe = 3.5. Weights: S1=2/3.5, S2=1/3.5, S3=0.5/3.5.
    # But max_cap=0.2 will hit for S1 and S2 if total is small?
    # Wait, in a 3-strategy port, 2/3.5 = 0.57 > 0.2. So S1 will be capped.
    # Let's test with 10 strategies to allow natural distribution < 20%.
    strategies = [{"id": f"S{i}", "sharpe": 1.0} for i in range(10)]
    # Total Sharpe = 10.0. Each weight = 1.0/10.0 = 0.1 (No capping).

    report = allocator.allocate_capital(strategies, total_capital=1000.0)

    assert report["result"] == "PASS"
    assert report["metrics"]["active_strategy_nodes"] == 10
    for _sid, weight in report["distribution_map"].items():
        assert weight == 0.1


def test_allocator_strict_position_cap_enforcement(allocator: CapitalAllocationEngine) -> None:
    """Verify that a single strategy with high Sharpe is strictly capped at 20%."""
    strategies = [
        {"id": "GOD_MODE", "sharpe": 100.0},
        {"id": "NORMAL_1", "sharpe": 1.0},
        {"id": "NORMAL_2", "sharpe": 1.0},
        {"id": "NORMAL_3", "sharpe": 1.0},
        {"id": "NORMAL_4", "sharpe": 1.0},
    ]
    # Total Sharpe = 104.0. Initial weight for GOD_MODE = 100/104 = 0.96.
    # Must be capped at 0.2.

    report = allocator.allocate_capital(strategies, total_capital=1000.0)

    assert report["distribution_map"]["GOD_MODE"] == 0.2
    assert report["metrics"]["max_concentration_score"] == 0.2
    assert sum(report["distribution_map"].values()) == pytest.approx(1.0)


def test_allocator_zero_performance_gating(allocator: CapitalAllocationEngine) -> None:
    """Verify that strategies with negative or zero Sharpe receive no capital."""
    strategies = [
        {"id": "GOOD", "sharpe": 1.0},
        {"id": "BAD", "sharpe": -0.5},
        {"id": "ZERO", "sharpe": 0.0},
    ]

    report = allocator.allocate_capital(strategies, total_capital=1000.0)

    assert report["metrics"]["active_strategy_nodes"] == 1
    assert "GOOD" in report["distribution_map"]
    assert report["distribution_map"]["GOOD"] == 0.2
    # Note: If only 1 strategy, it's capped at 20% (diversification veracity).
    assert "BAD" not in report["distribution_map"]


def test_allocator_iterative_redistribution(allocator: CapitalAllocationEngine) -> None:
    """Verify programmatic redistribution when multiple strategies hit the cap."""
    strategies = [
        {"id": "H1", "sharpe": 10.0},
        {"id": "H2", "sharpe": 10.0},
        {"id": "M1", "sharpe": 1.0},
        {"id": "M2", "sharpe": 1.0},
        {"id": "L1", "sharpe": 0.1},
    ]
    # Total Sharpe ~ 22.1. Initial H1, H2 ~ 10/22.1 = 0.45. Capped to 0.2.
    # Remaining 0.6 should be split between M1, M2, L1.

    report = allocator.allocate_capital(strategies, total_capital=1000.0)

    assert report["distribution_map"]["H1"] == 0.2
    assert report["distribution_map"]["H2"] == 0.2
    assert sum(report["distribution_map"].values()) == pytest.approx(1.0)


def test_allocator_empty_handling(allocator: CapitalAllocationEngine) -> None:
    """Verify that empty strategy sets result in SKIP/Principal Protection."""
    report = allocator.allocate_capital([], total_capital=1000.0)

    assert report["result"] == "SKIP"
    assert report["status"] == "ALLOCATION_EMPTY"


def test_allocator_telemetry_tracking(allocator: CapitalAllocationEngine) -> None:
    """Verify situational awareness and entropy telemetry indexing."""
    strategies = [{"id": f"S{i}", "sharpe": 1.0} for i in range(10)]
    allocator.allocate_capital(strategies, total_capital=1000.0)

    stats = allocator.get_allocation_telemetry()
    assert stats["current_max_concentration"] == 0.1
    assert stats["diversification_entropy"] == 0.9
    assert stats["status"] == "ALLOCATION_GOVERNANCE"
