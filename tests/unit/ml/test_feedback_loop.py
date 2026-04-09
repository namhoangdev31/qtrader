import time

import numpy as np
import pytest

from qtrader.ml.feedback_loop import FeedbackController


@pytest.fixture
def controller() -> FeedbackController:
    """Initialize FeedbackController with industrial defaults (60s delay)."""
    return FeedbackController(min_fill_pct=0.9, max_slippage_bps=50.0, delay_window_s=60)


def test_feedback_high_quality_authorization(controller: FeedbackController) -> None:
    """Verify that a high-quality, mature trade is properly attributed."""
    signal = {"id": "S123", "features": np.array([1.0, 2.0])}

    # Trade: Mature (settled 2 mins ago), Perfect Fill, Nominal Slippage
    trade = {
        "timestamp": time.time() - 120,
        "settled_at": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 100.1,  # 10bps slippage < 50bps
        "total_qty": 10.0,
        "filled_qty": 10.0,  # 100% fill > 90%
        "entry_price": 90.0,
        "exit_price": 110.0,
        "fees": 2.0,
    }

    sample = controller.process_trade(trade, signal)
    assert sample is not None
    assert sample.signal_id == "S123"
    # PnL = (110 - 90) * 10 = 200. Fees = 2.0 -> Net = 198.0
    assert sample.net_reward == 198.0


def test_feedback_immature_rejection(controller: FeedbackController) -> None:
    """Verify that immature trades (within delay window) are rejected to prevent leakage."""
    signal = {"id": "S123", "features": np.array([1.0])}

    # Trade: Settlement just happened (5s ago) < 60s delay
    trade = {
        "timestamp": time.time() - 5,
        "requested_price": 100.0,
        "avg_price": 100.0,
        "total_qty": 10.0,
        "filled_qty": 10.0,
        "entry_price": 100.0,
        "exit_price": 101.0,
    }

    sample = controller.process_trade(trade, signal)
    assert sample is None


def test_feedback_noise_rejection_slippage(controller: FeedbackController) -> None:
    """Verify that trades with extreme slippage (> 50bps) are filtered as noise."""
    signal = {"id": "S123", "features": np.array([1.0])}

    # Trade: High Slippage (100.0 -> 101.0 = 100bps > 50bps)
    trade = {
        "timestamp": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 101.0,  # 100bps slippage
        "total_qty": 10.0,
        "filled_qty": 10.0,
        "entry_price": 100.0,
        "exit_price": 101.0,
    }

    sample = controller.process_trade(trade, signal)
    assert sample is None


def test_feedback_noise_rejection_fill(controller: FeedbackController) -> None:
    """Verify that trades with low fill rate (< 90%) are filtered as noise."""
    signal = {"id": "S123", "features": np.array([1.0])}

    # Trade: Poor Fill (5.0 / 10.0 = 50% < 90%)
    trade = {
        "timestamp": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 100.0,
        "total_qty": 10.0,
        "filled_qty": 5.0,  # 50% fill
        "entry_price": 100.0,
        "exit_price": 101.0,
    }

    sample = controller.process_trade(trade, signal)
    assert sample is None


def test_feedback_telemetry(controller: FeedbackController) -> None:
    """Verify feedback quality situational awareness report."""
    signal = {"id": "S1", "features": np.array([0])}

    # 1. OK trade
    trade_ok = {
        "timestamp": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 100.0,
        "total_qty": 10.0,
        "filled_qty": 10.0,
        "entry_price": 100.0,
        "exit_price": 101.0,
    }
    controller.process_trade(trade_ok, signal)

    # 2. Noise trade (No fill)
    trade_noise = trade_ok.copy()
    trade_noise["filled_qty"] = 0.0
    controller.process_trade(trade_noise, signal)

    report = controller.get_feedback_report()
    assert report["processed_count"] == 2
    assert report["noise_ratio"] == 0.5
