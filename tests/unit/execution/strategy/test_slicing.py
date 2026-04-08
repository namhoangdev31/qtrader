from datetime import datetime
from unittest import mock

import pytest

from qtrader.execution.strategy.slicing import AdaptiveSlicer, SlicingState


@pytest.fixture
def execution_config() -> mock.MagicMock:
    """Mock execution configuration with slicing parameters."""
    cfg = mock.MagicMock()
    # Path configuration alignment
    cfg.routing = {"slicing": {"max_participation_rate": 0.1, "urgency_sensitivity": 1.5}}
    return cfg


def test_slicer_acceleration_on_imbalance(execution_config: mock.MagicMock) -> None:
    """Verify that slicer accelerates when imbalance favors the side."""
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    order.symbol = "BTCUSDT"
    order.order_id = "parent_1"

    # State: 50% time elapsed, 50% quantity remaining.
    state = SlicingState(
        remaining_qty=500.0,
        elapsed_time_sec=30.0,
        total_duration_sec=60.0,
        last_update=datetime.now(),
    )

    # Signal: High Positive Imbalance (0.8) for BUY.
    signals = {"imbalance": 0.8, "toxicity": 0.1, "spread_ratio": 1.0, "level_volume": 10000.0}

    child = slicer.generate_slice(order, state, signals)

    assert child is not None
    # Neutral slice = 1000 * 0.05 * 1.0 = 50.
    # Adaptive urgency = 1.0 + (0.8 * 1 * 1.5) = 2.2.
    # Target = 50 * 2.2 = 110.
    assert child.quantity == pytest.approx(110.0)
    assert child.side == "BUY"


def test_slicer_suppression_on_toxicity(execution_config: mock.MagicMock) -> None:
    """Verify that slicer suppresses activity during toxic flow."""
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"
    order.symbol = "BTCUSDT"

    state = SlicingState(500.0, 30.0, 60.0, datetime.now())

    # Signal: High Toxicity (0.9).
    signals = {"imbalance": 0.0, "toxicity": 0.9, "spread_ratio": 1.0}

    child = slicer.generate_slice(order, state, signals)

    # Decelerated slice = 50 * 0.1 = 5.
    assert child is not None
    assert child.quantity == pytest.approx(5.0)


def test_slicer_participation_cap(execution_config: mock.MagicMock) -> None:
    """Verify that slicer enforces participation rate limits."""
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"

    state = SlicingState(500.0, 30.0, 60.0, datetime.now())

    # Low level volume (20 units). Max participation = 10% = 2 units.
    signals = {"imbalance": 0.0, "toxicity": 0.1, "level_volume": 20.0}

    child = slicer.generate_slice(order, state, signals)

    assert child is not None
    assert child.quantity == pytest.approx(2.0)


def test_slicer_catastrophic_safety(execution_config: mock.MagicMock) -> None:
    """Verify industrial safety and failsafe behavior."""
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0

    # 1. Zero duration or time
    state = SlicingState(100.0, 0.0, 0.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.1}
    assert slicer.generate_slice(order, state, signals) is not None

    # 2. Complete fill
    state = SlicingState(0.0, 30.0, 60.0, datetime.now())
    assert slicer.generate_slice(order, state, signals) is None

    # 3. Malformed signals (None causing TypeError)
    assert slicer.generate_slice(order, None, None) is None  # type: ignore


def test_slicer_schedule_alignment(execution_config: mock.MagicMock) -> None:
    """Verify that slicer pushes harder when behind schedule."""
    slicer = AdaptiveSlicer(execution_config)
    order = mock.MagicMock()
    order.quantity = 1000.0
    order.action = "BUY"

    # BEHIND: 90% time elapsed, but 90% quantity remaining (only 10% filled).
    state = SlicingState(900.0, 54.0, 60.0, datetime.now())
    signals = {"imbalance": 0.0, "toxicity": 0.1}

    child = slicer.generate_slice(order, state, signals)

    # Schedule deviation = 0.9 - 0.1 = 0.8.
    # Target = 50 * 1.0 * (1.0 + 0.8) = 90.
    assert child is not None
    assert child.quantity == pytest.approx(90.0)
