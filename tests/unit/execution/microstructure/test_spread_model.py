from statistics import StatisticsError
from unittest import mock

import pytest

from qtrader.execution.microstructure.spread_model import SpreadDynamicsModel


@pytest.fixture
def execution_config() -> mock.MagicMock:
    """Mock execution configuration with spread model parameters."""
    cfg = mock.MagicMock()
    cfg.microstructure = {
        "spread_model": {
            "window_size": 10,
            "alpha": 0.5,
            "beta": 0.05
        }
    }
    return cfg


def test_spread_model_volatility_widening(execution_config: mock.MagicMock) -> None:
    """Verify that spread increases as mid-price volatility spikes."""
    model = SpreadDynamicsModel(execution_config)
    
    # Static mid-price initially
    # Need 5 samples for prediction to activate
    current_spread = 0.01
    last_pred = 0.0
    for _ in range(5):
        last_pred = model.update(bid=100.0, ask=100.01, volume=0.0)

    assert last_pred == pytest.approx(current_spread)  # noqa: S101
    
    # Introduce volatility (spike)
    # T6: Mid=90.005, T7: Mid=110.005. Significant volatility move.
    model.update(bid=90.0, ask=90.01, volume=0.0)
    pred_spread = model.update(bid=110.0, ask=110.01, volume=0.0)

    # Predicted spread should widen due to alpha * volatility
    assert pred_spread > current_spread  # noqa: S101


def test_spread_model_liquidity_tightening(execution_config: mock.MagicMock) -> None:
    """Verify that spread decreases as book liquidity increases."""
    model = SpreadDynamicsModel(execution_config)
    
    # 5 neutral samples
    for _ in range(5):
        model.update(bid=100.0, ask=100.01, volume=0.0)
    
    # High liquidity (volume=1.0) with zero volatility
    # S_{t+1} = 0.01 + 0 - (0.05 * 1.0) = -0.04 -> Floor at min_spread
    pred_spread = model.update(bid=100.0, ask=100.01, volume=1.0)
    
    min_spread = 1e-8
    assert pred_spread == pytest.approx(min_spread)  # noqa: S101


def test_spread_model_catastrophic_safety(execution_config: mock.MagicMock) -> None:
    """Verify industrial safety and failsafe behavior."""
    model = SpreadDynamicsModel(execution_config)
    
    # 1. Zero liquidity
    assert model.update(100.0, 100.01, 0.0) == pytest.approx(0.01)  # noqa: S101
    
    # 2. Level sweep (Ask-Bid widening)
    # T1-T5: Normal spread
    for _ in range(5):
        model.update(100.0, 100.01, 0.0)
    
    # Spread suddenly widens. Ensure liquidity is 0 so it doesn't offset widening.
    pred = model.update(100.0, 101.0, 0.0)
    # Prediction is CurrentSpread (1.0) + Alpha*Vol. Must be >= 1.0.
    assert pred >= 1.0  # noqa: S101

    # 3. Malformed inputs (None causing TypeError in math)
    # This triggers the Exception block
    model.reset()
    model.update(100.0, 100.01, 10.0)
    assert model.update(None, 100.01, 10.0) == pytest.approx(0.01)  # type: ignore # noqa: S101


def test_spread_model_statistics_failure(execution_config: mock.MagicMock) -> None:
    """Verify StatisticsError handling for insufficient data."""
    model = SpreadDynamicsModel(execution_config)
    
    # Manual patch to force StatisticsError
    with mock.patch("statistics.stdev", side_effect=StatisticsError):
        # Window size 5 triggers prediction step
        for _ in range(5):
            model.update(100.0, 100.01, 0.0)
        
        # Predicted spread should fallback (currentspread + 0 - 0)
        assert model.update(100.0, 100.01, 0.0) == pytest.approx(0.01)  # noqa: S101


def test_spread_model_reset(execution_config: mock.MagicMock) -> None:
    """Verify state reset for industrial lifecycle management."""
    model = SpreadDynamicsModel(execution_config)
    model.update(100.0, 100.01, 10.0)
    
    assert len(model._mid_prices) > 0  # noqa: S101
    model.reset()
    assert len(model._mid_prices) == 0  # noqa: S101
