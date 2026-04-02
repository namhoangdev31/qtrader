from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from qtrader.core.events import EventType
from qtrader.execution.objective import ExecutionObjective

# Test Constants
STRATEGY_ID = "RL_STRAT_01"


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with objective parameters."""
    cfg = MagicMock()
    cfg.objective = {
        "impact_k": 0.1,
        "impact_alpha": 0.5,
        "timing_lambda": 0.01,
        "risk_gamma": 0.1,
        "base_fee": 0.0001,
    }
    return cfg


@pytest.mark.asyncio
async def test_execution_objective_compute_success(execution_config: MagicMock) -> None:
    """Verify objective function computation for industrial-grade execution optimization."""
    bus = AsyncMock()
    obj = ExecutionObjective(execution_config, bus)

    # Market State S_t
    state = {
        "symbol": "BTC_USDT",
        "liquidity": 1000.0,
        "spread_pct": 0.0002,  # 2bps
        "volatility": 0.01,
    }

    # Execution Action a_t
    action = {"order_size": 100.0, "delay": 1.0, "venue": "binance"}

    cost = await obj.compute(state, action, STRATEGY_ID)

    # 1. Validation of Impact (k * (100/1000)^0.5 = 0.1 * 0.316 = 0.0316)
    # 2. Validation of Timing (lambda * 1 = 0.01)
    # 3. Validation of Fees (0.0001 * 100 + 0.0002 * 100 / 2 = 0.01 + 0.01 = 0.02)
    # 4. Validation of Risk (gamma * (100 * 0.01)^2 = 0.1 * 1.0 = 0.1)
    # Total => 0.0316 + 0.01 + 0.02 + 0.1 = 0.1616

    assert cost > 0
    assert cost == pytest.approx(0.1616227766)

    # 5. Validation of Event Bus Publish
    assert bus.publish.called
    assert bus.publish.call_args[0][0].event_type == EventType.EXECUTION_OBJECTIVE


@pytest.mark.asyncio
async def test_execution_objective_differentiability(execution_config: MagicMock) -> None:
    """Verify that the objective function is smooth and differentiable for RL optimization."""
    obj = ExecutionObjective(execution_config)

    state = {"liquidity": 1000.0, "spread_pct": 0.0002, "volatility": 0.01}

    # 1. Numerical Gradient
    size_a = 100.0
    size_b = 100.0001

    cost_a = await obj.compute(state, {"order_size": size_a})
    cost_b = await obj.compute(state, {"order_size": size_b})

    numerical_grad = (cost_b - cost_a) / (size_b - size_a)
    assert np.isfinite(numerical_grad)

    # 2. Analytical Gradient
    analytical_grad = obj.compute_impact_derivative(state, {"order_size": size_a})
    # Analytical deriv: 0.000158113
    assert analytical_grad == pytest.approx(0.000158113, abs=1e-6)

    # 3. Zero Boundary Check
    zero_grad = obj.compute_impact_derivative(state, {"order_size": 0.0})
    assert zero_grad == 0.0


@pytest.mark.asyncio
async def test_execution_objective_zero_liquidity_safety(execution_config: MagicMock) -> None:
    """Verify failsafe behavior during catastrophic liquidity drops."""
    obj = ExecutionObjective(execution_config)

    # Zero Liquidity state
    state = {"liquidity": 0.0}
    action = {"order_size": 100.0}

    cost = await obj.compute(state, action)

    # Failsafe should prevent NaN/Inf by defaulting liquidity to 1.0
    assert np.isfinite(cost)
    assert cost > 0


@pytest.mark.asyncio
async def test_execution_objective_failure_handling(execution_config: MagicMock) -> None:
    """Verify industrial error recovery from malformed execution states."""
    obj = ExecutionObjective(execution_config)

    # Malformed state (missing key causing TypeError in math)
    state = None  # type: ignore

    cost = await obj.compute(state, {"order_size": 100.0})

    # Should return large finite cost on failure
    fail_cost = 1e18
    assert cost == fail_cost
