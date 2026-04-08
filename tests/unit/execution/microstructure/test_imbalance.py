from unittest.mock import MagicMock

import pytest

from qtrader.execution.microstructure.imbalance import OrderbookImbalance


@pytest.fixture
def execution_config() -> MagicMock:
    """Mock execution configuration with microstructure parameters."""
    cfg = MagicMock()
    cfg.microstructure = {"imbalance": {"n_levels": 5, "lambda_decay": 0.5}}
    return cfg


def test_orderbook_imbalance_compute_success(execution_config: MagicMock) -> None:
    """Verify weighted imbalance computation for multi-level orderbooks."""
    model = OrderbookImbalance(execution_config)

    # 1. Neutral Book
    bids = [[100, 10], [99, 10], [98, 10], [97, 10], [96, 10]]
    asks = [[101, 10], [102, 10], [103, 10], [104, 10], [105, 10]]
    assert model.compute(bids, asks) == 0.0

    # 2. Bid-Heavy Book (Buy pressure)
    bids = [[100, 20], [99, 20], [98, 20], [97, 20], [96, 20]]
    asks = [[101, 10], [102, 10], [103, 10], [104, 10], [105, 10]]
    imbalance = model.compute(bids, asks)
    target_pos = 0.3
    assert imbalance > target_pos
    assert imbalance == pytest.approx(0.333333333)

    # 3. Ask-Heavy Book (Sell pressure)
    bids = [[100, 10]]
    asks = [[101, 100]]
    imbalance = model.compute(bids, asks)
    target_neg = -0.8
    assert imbalance < target_neg


def test_orderbook_imbalance_weighted_decay(execution_config: MagicMock) -> None:
    """Verify that depth decay correctly prioritizes top-of-book levels."""
    model = OrderbookImbalance(execution_config)

    # Book A: 100 on level 0 bid, 10 on level 0 ask
    # Book B: 10 on level 0 bid, 100 on level 4 ask
    bids_a = [[100, 100]]
    asks_a = [[101, 10]]

    bids_b = [[100, 10]]
    asks_b = [[101, 0], [102, 0], [103, 0], [104, 0], [105, 100]]  # Level 4

    # Book A should have much higher imbalance than Book B
    imb_a = model.compute(bids_a, asks_a)
    imb_b = model.compute(bids_b, asks_b)

    assert imb_a > imb_b
    assert imb_b < 0


def test_orderbook_imbalance_catastrophic_safety(execution_config: MagicMock) -> None:
    """Verify failsafe behavior during missing or zero-volume books."""
    model = OrderbookImbalance(execution_config)

    # Empty book
    assert model.compute([], []) == 0.0

    # Zero volume
    assert model.compute([[100, 0]], [[101, 0]]) == 0.0

    # Malformed book
    assert model.compute(None, None) == 0.0  # type: ignore
