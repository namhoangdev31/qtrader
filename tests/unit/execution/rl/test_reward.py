from unittest.mock import MagicMock

import pytest

from qtrader.execution.rl.reward import ExecutionRewardFunction


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with reward baseline parameters."""
    cfg = MagicMock()
    # RL Reward Parameters
    cfg.rl = {"reward": {"fill_bonus_weight": 100.0, "toxicity_penalty_weight": 50.0}}
    return cfg


def test_execution_reward_cost_monotonicity(execution_config: MagicMock) -> None:
    """Verify that higher execution costs result in lower (more negative) rewards."""
    model = ExecutionRewardFunction(execution_config)

    # 2 scenarios: High Cost (100) vs Low Cost (1)
    # Identical order value, fill, and toxicity
    market_state = {"toxicity_score": 0.0}

    res_high = {"total_cost": 100.0, "order_value": 100000.0, "filled_qty": 1.0, "total_qty": 1.0}
    res_low = {"total_cost": 1.0, "order_value": 100000.0, "filled_qty": 1.0, "total_qty": 1.0}

    r_high = model.compute(res_high, market_state)
    r_low = model.compute(res_low, market_state)

    # Cost should be more negative in the High-Cost scenario
    assert r_high < r_low


def test_execution_reward_fill_bonus(execution_config: MagicMock) -> None:
    """Verify that achieving 100% fill rate provides a positive bonus."""
    model = ExecutionRewardFunction(execution_config)

    # 2 scenarios: Full Fill (1.0) vs Partial Fill (0.5)
    # Identical zero cost and zero toxicity
    market_state = {"toxicity_score": 0.0}

    res_full = {"total_cost": 0.0, "order_value": 100.0, "filled_qty": 10.0, "total_qty": 10.0}
    res_half = {"total_cost": 0.0, "order_value": 100.0, "filled_qty": 5.0, "total_qty": 10.0}

    r_full = model.compute(res_full, market_state)
    r_half = model.compute(res_half, market_state)

    # Reward difference should be equal to the fill bonus (beta * 0.5)
    # beta = 100.0, so difference = 50.0
    assert r_full - r_half == pytest.approx(50.0)
    assert r_full == pytest.approx(100.0)


def test_execution_reward_toxicity_penalty(execution_config: MagicMock) -> None:
    """Verify that trading during high-toxicity periods reduces the reward signal."""
    model = ExecutionRewardFunction(execution_config)

    # 2 scenarios: Toxic (1.0) vs Clean (0.0)
    # Identical zero cost and full fill
    res = {"total_cost": 0.0, "order_value": 100.0, "filled_qty": 1.0, "total_qty": 1.0}

    # gamma = 50.0, beta = 100.0
    r_toxic = model.compute(res, {"toxicity_score": 1.0})
    r_clean = model.compute(res, {"toxicity_score": 0.0})

    # Final reward: R = -0 + (100 * 1.0) - (50 * toxicity)
    # R_clean = 100.0, R_toxic = 50.0
    assert r_toxic < r_clean
    assert r_toxic == pytest.approx(50.0)


def test_execution_reward_failsafe_recovery(execution_config: MagicMock) -> None:
    """Verify logic for zero order value and malformed market inputs."""
    model = ExecutionRewardFunction(execution_config)

    # 1. Zero order value: Should not divide by zero
    res_zero = {"total_cost": 1.0, "order_value": 0.0, "filled_qty": 1.0}
    r_zero = model.compute(res_zero, {})
    assert r_zero >= 0.0

    # 2. Extreme results: Should clip reward at 1000.0
    # Cost = 1,000,000 (bps = -1,000,000)
    res_extreme = {"total_cost": 100.0, "order_value": 0.1, "filled_qty": 0.0}
    r_extreme = model.compute(res_extreme, {})
    assert r_extreme == -1000.0

    # 3. Malformed result (None): Error handling
    assert model.compute(None, None) == 0.0  # type: ignore
