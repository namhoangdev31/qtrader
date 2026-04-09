from unittest.mock import MagicMock
import pytest
from qtrader.execution.strategy.scheduler import ExecutionScheduler


@pytest.fixture
def execution_config() -> MagicMock:
    cfg = MagicMock()
    cfg.routing = {"scheduler": {"risk_aversion": 0.1, "convergence_tol": 1e-06}}
    cfg.cost_model = {"impact_k": 0.15}
    return cfg


def test_scheduler_liquidity_following(execution_config: MagicMock) -> None:
    scheduler = ExecutionScheduler(execution_config)
    states = [
        {"liquidity": 100.0, "spread": 0.0, "volatility": 0.0},
        {"liquidity": 1000.0, "spread": 0.0, "volatility": 0.0},
    ]
    schedule = scheduler.optimize_schedule(100.0, states)
    assert len(schedule) == 2
    assert sum(schedule) == pytest.approx(100.0)
    assert schedule[1] > schedule[0]


def test_scheduler_risk_aversion_frontloading(execution_config: MagicMock) -> None:
    execution_config.routing["scheduler"]["risk_aversion"] = 1.0
    scheduler = ExecutionScheduler(execution_config)
    states = [
        {"liquidity": 500.0, "spread": 0.0, "volatility": 1.0},
        {"liquidity": 500.0, "spread": 0.0, "volatility": 1.0},
    ]
    schedule = scheduler.optimize_schedule(100.0, states)
    assert schedule[0] == pytest.approx(50.0)
    states_diff_vol = [
        {"liquidity": 500.0, "spread": 0.1, "volatility": 0.1},
        {"liquidity": 500.0, "spread": 0.1, "volatility": 5.0},
    ]
    schedule_vol = scheduler.optimize_schedule(100.0, states_diff_vol)
    assert schedule_vol[1] > schedule_vol[0]


def test_scheduler_catastrophic_safety(execution_config: MagicMock) -> None:
    scheduler = ExecutionScheduler(execution_config)
    assert scheduler.optimize_schedule(0.0, [{"liq": 10.0}]) == []
    assert scheduler.optimize_schedule(100.0, []) == []
    assert scheduler.optimize_schedule(100.0, [{"liquidity": 1.0}]) == [100.0]
    malformed = [{"liquidity": "INVALID"}, {"none": 10}]
    schedule = scheduler.optimize_schedule(100.0, malformed)
    assert len(schedule) == 2
    assert schedule[0] == 50.0


def test_scheduler_zero_liquidity_floor(execution_config: MagicMock) -> None:
    scheduler = ExecutionScheduler(execution_config)
    states = [
        {"liquidity": 0.0, "spread": 0.01, "volatility": 0.0},
        {"liquidity": 1000.0, "spread": 0.01, "volatility": 0.0},
    ]
    schedule = scheduler.optimize_schedule(100.0, states)
    assert schedule[1] > schedule[0]
    assert sum(schedule) == pytest.approx(100.0)
