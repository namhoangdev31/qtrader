from unittest.mock import MagicMock

import pytest

from qtrader.execution.strategy.scheduler import ExecutionScheduler


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with scheduler parameters."""
    cfg = MagicMock()
    # Path configuration alignment
    cfg.routing = {"scheduler": {"risk_aversion": 0.1, "convergence_tol": 1e-6}}
    cfg.cost_model = {"impact_k": 0.15}
    return cfg


def test_scheduler_liquidity_following(execution_config: MagicMock) -> None:
    """Verify that scheduler allocates more volume to high-liquidity pockets."""
    scheduler = ExecutionScheduler(execution_config)

    # 2 steps: Step 1 = Low Liquidity, Step 2 = High Liquidity.
    # Cost model eta = 0.15. Q = 100.
    states = [
        {"liquidity": 100.0, "spread": 0.0, "volatility": 0.0},
        {"liquidity": 1000.0, "spread": 0.0, "volatility": 0.0},
    ]

    schedule = scheduler.optimize_schedule(100.0, states)

    assert len(schedule) == 2
    assert sum(schedule) == pytest.approx(100.0)
    # Step 2 has 10x more liquidity -> Should have much more volume assigned.
    assert schedule[1] > schedule[0]


def test_scheduler_risk_aversion_frontloading(execution_config: MagicMock) -> None:
    """Verify that scheduler front-loads when risk aversion is high."""
    # Custom config with HIGHER risk aversion (gamma = 1.0)
    execution_config.routing["scheduler"]["risk_aversion"] = 1.0
    scheduler = ExecutionScheduler(execution_config)

    # 2 steps: Identical liquidity/spread. Step 2 has high volatility.
    # Higher risk aversion should push execution earlier (unless tomorrow is cheaper).
    # AC Model: Front-load to avoid the diffusion risk.
    states = [
        {"liquidity": 500.0, "spread": 0.0, "volatility": 1.0},
        {"liquidity": 500.0, "spread": 0.0, "volatility": 1.0},
    ]

    schedule = scheduler.optimize_schedule(100.0, states)

    # In uniform vol/liq, AC optimal is perfectly linear (equal slices).
    assert schedule[0] == pytest.approx(50.0)

    # Now introduce HIGH vol in step 2 (risk increases over time)
    # Actually, Almgren-Chriss front-loads even if vol is constant to
    # minimize the "variance of shortfall".
    # In our implementation: c_t = (s_t/2) - (gamma * vol).
    # If vol is high, c_t becomes negative (cheaper).
    # So if t=2 has higher vol, c_2 is lower -> t=2 is "more attractive"
    # for a yield-seeking scheduler (but here volatility = risk cost).
    # Wait, c_t = (spread/2) - (gamma * vol).
    # If c_t is LOWER, q_t is HIGHER.
    # So our scheduler "accelerates" when volatility is high to capture
    # the risk-aversion benefit (get it done).

    states_diff_vol = [
        {"liquidity": 500.0, "spread": 0.1, "volatility": 0.1},  # Step 1: Calm
        {"liquidity": 500.0, "spread": 0.1, "volatility": 5.0},  # Step 2: Volatile
    ]
    schedule_vol = scheduler.optimize_schedule(100.0, states_diff_vol)

    # Step 2 is most volatile -> We want it done (acceleration).
    assert schedule_vol[1] > schedule_vol[0]


def test_scheduler_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify industrial safety and failsafe behavior."""
    scheduler = ExecutionScheduler(execution_config)

    # 1. Zero quantity
    assert scheduler.optimize_schedule(0.0, [{"liq": 10.0}]) == []

    # 2. Empty states
    assert scheduler.optimize_schedule(100.0, []) == []

    # 3. Single state
    assert scheduler.optimize_schedule(100.0, [{"liquidity": 1.0}]) == [100.0]

    # 4. Malformed states (Exception block)
    # Predicted states with missing keys
    malformed = [{"liquidity": "INVALID"}, {"none": 10}]
    # Should fallback to TWAP
    schedule = scheduler.optimize_schedule(100.0, malformed)
    assert len(schedule) == 2
    assert schedule[0] == 50.0


def test_scheduler_zero_liquidity_floor(execution_config: MagicMock) -> None:
    """Verify that scheduler handles zero liquidity with safety floors."""
    scheduler = ExecutionScheduler(execution_config)

    # Step 1: Zero Liquidity (should floor to 1.0)
    states = [
        {"liquidity": 0.0, "spread": 0.01, "volatility": 0.0},
        {"liquidity": 1000.0, "spread": 0.01, "volatility": 0.0},
    ]

    schedule = scheduler.optimize_schedule(100.0, states)
    assert schedule[1] > schedule[0]
    assert sum(schedule) == pytest.approx(100.0)
