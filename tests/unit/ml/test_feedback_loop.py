import time
import numpy as np
import pytest
from qtrader.ml.feedback_loop import FeedbackController


@pytest.fixture
def controller() -> FeedbackController:
    return FeedbackController(min_fill_pct=0.9, max_slippage_bps=50.0, delay_window_s=60)


def test_feedback_high_quality_authorization(controller: FeedbackController) -> None:
    signal = {"id": "S123", "features": np.array([1.0, 2.0])}
    trade = {
        "timestamp": time.time() - 120,
        "settled_at": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 100.1,
        "total_qty": 10.0,
        "filled_qty": 10.0,
        "entry_price": 90.0,
        "exit_price": 110.0,
        "fees": 2.0,
    }
    sample = controller.process_trade(trade, signal)
    assert sample is not None
    assert sample.signal_id == "S123"
    assert sample.net_reward == 198.0


def test_feedback_immature_rejection(controller: FeedbackController) -> None:
    signal = {"id": "S123", "features": np.array([1.0])}
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
    signal = {"id": "S123", "features": np.array([1.0])}
    trade = {
        "timestamp": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 101.0,
        "total_qty": 10.0,
        "filled_qty": 10.0,
        "entry_price": 100.0,
        "exit_price": 101.0,
    }
    sample = controller.process_trade(trade, signal)
    assert sample is None


def test_feedback_noise_rejection_fill(controller: FeedbackController) -> None:
    signal = {"id": "S123", "features": np.array([1.0])}
    trade = {
        "timestamp": time.time() - 120,
        "requested_price": 100.0,
        "avg_price": 100.0,
        "total_qty": 10.0,
        "filled_qty": 5.0,
        "entry_price": 100.0,
        "exit_price": 101.0,
    }
    sample = controller.process_trade(trade, signal)
    assert sample is None


def test_feedback_telemetry(controller: FeedbackController) -> None:
    signal = {"id": "S1", "features": np.array([0])}
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
    trade_noise = trade_ok.copy()
    trade_noise["filled_qty"] = 0.0
    controller.process_trade(trade_noise, signal)
    report = controller.get_feedback_report()
    assert report["processed_count"] == 2
    assert report["noise_ratio"] == 0.5
