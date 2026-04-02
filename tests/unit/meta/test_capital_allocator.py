import numpy as np
import polars as pl
import pytest

from qtrader.meta.capital_allocator import CapitalAllocator


@pytest.fixture
def allocator() -> CapitalAllocator:
    """Initialize CapitalAllocator with industrial defaults (5% cap)."""
    return CapitalAllocator(max_position_pct=0.05, target_capital=1.0)


def test_allocation_normalization_rich(allocator: CapitalAllocator) -> None:
    """Verify that the sum of weights is 100% when there are enough strategies."""
    # 40 strategies, each having 1/40 = 2.5% weight (under 5% cap)
    scores = [1.0] * 40
    weights = allocator.allocate(scores)

    assert sum(weights) == pytest.approx(1.0)
    assert all(w == 0.025 for w in weights)


def test_allocation_individual_cap_redistribution(allocator: CapitalAllocator) -> None:
    """Verify that excess weights from capped strategies are redistributed."""
    # 40 strategies. Strategy 0 has massive score.
    scores = [100.0] + [1.0] * 39
    weights = allocator.allocate(scores)

    # S0 must be capped at 5%
    assert weights[0] == pytest.approx(0.05)
    assert sum(weights) == pytest.approx(1.0)
    assert weights[1] == pytest.approx(0.95 / 39)


def test_allocation_correlation_penalty_diversified(allocator: CapitalAllocator) -> None:
    """Verify that correlation penalty works when not hitting exposure caps."""
    scores = [1.0] * 40

    corr_data = np.eye(40)
    corr_data[0, 1] = 1.0
    corr_data[1, 0] = 1.0

    corr_matrix = pl.DataFrame(corr_data, schema=[f"S{i}" for i in range(40)])

    weights = allocator.allocate(scores, corr_matrix=corr_matrix)

    assert weights[2] > weights[0]
    assert weights[2] > weights[1]
    assert sum(weights) == pytest.approx(1.0)


def test_allocation_under_utilization_scenario(allocator: CapitalAllocator) -> None:
    """Verify that too few strategies lead to under-utilization if individual caps are strict."""
    # 10 strategies, all capped at 5% = 50% max exposure total
    scores = [10.0] * 10
    weights = allocator.allocate(scores)

    assert sum(weights) == pytest.approx(0.5)
    assert all(w == 0.05 for w in weights)


def test_allocation_edge_cases(allocator: CapitalAllocator) -> None:
    """Verify robustness against zero-scores or missing data."""
    # 1. Zero scores
    weights_zero = allocator.allocate([0.0, 0.0])
    assert weights_zero == [0.05, 0.05]

    # 2. Empty input
    assert allocator.allocate([]) == []

    # 3. Correlation weight collapse
    scores = [1.0, 1.0]
    corr_matrix = pl.DataFrame({"S0": [1.0, 1.0], "S1": [1.0, 1.0]})
    weights_corr = allocator.allocate(scores, corr_matrix=corr_matrix)
    assert weights_corr[0] == 0.05


def test_allocation_hhi_telemetry(allocator: CapitalAllocator) -> None:
    """Verify the validity of the diversification report (HHI Index)."""
    scores = [1.0] * 100
    allocator.allocate(scores)

    report = allocator.get_allocation_report()
    assert report["hhi_index"] == pytest.approx(0.01)
    assert report["concentration_status"] == "DIVERSIFIED"


def test_allocation_convergence_and_empty_under(allocator: CapitalAllocator) -> None:
    """Verify redistribution convergence when all strategies hit the cap."""
    # Hit line 126 (empty under_mask)
    # n=20. S0=0.06. others=0.04947.
    # Total sum will be 1.0. S0 capped. Excess 0.01 distributed to others.
    # If they all hit 0.05, under_mask becomes empty.

    # Construct: n=20. Score S0=10.0, others=9.9
    # S0 raw = 10 / (10 + 19*9.9) = 10 / 198.1 approx 0.0504
    # Others raw = 9.9 / 198.1 approx 0.0499
    # S0 hits cap. Excess is very small (0.0004).
    # Distributed to others. 0.0004 / 19 approx 0.00002.
    # New weight others = 0.0499 + 0.00002 = 0.04992 (still under 0.05).

    # To force 126: n=20. S0=1.0, others=1.0.
    # n * 0.05 = 1.0. Early exit at 119.

    # If we have n=20 and one is 0.06 and others are 0.04999.
    # Then S0 becomes 0.05. excess 0.01. Distributed to others.
    # Others will exceed 0.05. Next iteration they all get capped.
    # under_mask will be empty.

    scores = [1.01] + [1.0] * 19
    weights = allocator.allocate(scores)
    assert all(w == pytest.approx(0.05) for w in weights)
    assert sum(weights) == pytest.approx(1.0)
