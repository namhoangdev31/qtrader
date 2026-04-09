from datetime import datetime
from unittest import mock
import pytest
from qtrader.execution.strategy.slicing import AdaptiveSlicer, SlicingState


@pytest.fixture
def execution_config() -> mock.MagicMock:
    cfg = mock.MagicMock()
    cfg.routing = {"slicing": {"max_participation_rate": 0.1, "urgency_sensitivity": 1.5}}
    return cfg


def test_slicer_acceleration_on_imbalance(execution_config: mock.MagicMock) -> None:
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    order.symbol = "BTCUSDT"
    order.order_id = "parent_1"
    state = SlicingState(
        remaining_qty=500.0,
        elapsed_time_sec=30.0,
        total_duration_sec=60.0,
        last_update=datetime.now(),
    )
    signals = {"imbalance": 0.8, "toxicity": 0.1, "spread_ratio": 1.0, "level_volume": 10000.0}
    child = slicer.generate_slice(order, state, signals)
    assert child is not None
    assert child.quantity == pytest.approx(110.0)
    assert child.side == "BUY"


def test_slicer_suppression_on_toxicity(execution_config: mock.MagicMock) -> None:
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    order.symbol = "BTCUSDT"
    state = SlicingState(500.0, 30.0, 60.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.9, "spread_ratio": 1.0}
    child = slicer.generate_slice(order, state, signals)
    assert child is not None
    assert child.quantity == pytest.approx(5.0)


def test_slicer_participation_cap(execution_config: mock.MagicMock) -> None:
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    state = SlicingState(500.0, 30.0, 60.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.1, "level_volume": 20.0}
    child = slicer.generate_slice(order, state, signals)
    assert child is not None
    assert child.quantity == pytest.approx(2.0)


def test_slicer_catastrophic_safety(execution_config: mock.MagicMock) -> None:
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    state = SlicingState(100.0, 0.0, 0.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.1}
    assert slicer.generate_slice(order, state, signals) is not None
    state = SlicingState(0.0, 30.0, 60.0, datetime.now())
    assert slicer.generate_slice(order, state, signals) is None
    assert slicer.generate_slice(order, None, None) is None


def test_slicer_schedule_alignment(execution_config: mock.MagicMock) -> None:
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    state = SlicingState(900.0, 54.0, 60.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.1}
    child = slicer.generate_slice(order, state, signals)
    assert child is not None
    assert child.quantity == pytest.approx(90.0)
