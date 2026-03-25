from datetime import datetime, timedelta

import polars as pl

from qtrader.hft.spoofing import SpoofingDetector

# ──────────────────────────────────────────────
# Fixtured Data
# ──────────────────────────────────────────────

START_TIME = datetime(2025, 1, 1, 10, 0, 0)

TEST_EVENTS = pl.DataFrame(
    {
        "timestamp": [
            START_TIME,
            START_TIME + timedelta(milliseconds=100),
            START_TIME + timedelta(milliseconds=200),
            START_TIME + timedelta(milliseconds=300),
            START_TIME + timedelta(milliseconds=400),
            START_TIME + timedelta(milliseconds=1000),
        ],
        "order_id": ["O1", "O2", "O1", "O3", "O3", "O2"],
        "type": [
            "NEW",  # O1: Large, Cancel at 200ms -> SPOOF (1000 vol)
            "NEW",  # O2: Large, Cancel at 1000ms -> NOT SPOOF (duration too long)
            "CANCEL",  # O1
            "NEW",  # O3: Large, Filled at 400ms -> NOT SPOOF (fill activity)
            "FILL",  # O3
            "CANCEL",  # O2
        ],
        "volume": [1000, 1000, 1000, 1000, 500, 1000],
    }
)

# Configuration for unit tests
THRESHOLD_VOL = 1000
MAX_CANCEL_MS = 500


def test_spoofing_detection_logic() -> None:
    """Verify that spoofing (quick cancel without fill) is correctly flagged."""
    detector = SpoofingDetector()
    flags = detector.detect_spoofing(
        TEST_EVENTS, large_order_vol=THRESHOLD_VOL, quick_cancel_ms=MAX_CANCEL_MS
    )

    # Should flag O1
    # Should NOT flag O2 (duration 900ms > 500ms)
    # Should NOT flag O3 (has FILL event)
    expected_orders = ["O1"]
    assert flags.height == 1
    assert flags["order_id"][0] == expected_orders[0]

    # Check duration calculation (200ms - 0ms)
    expected_dur = 200
    assert flags["duration_ms"][0] == expected_dur


def test_spoofing_threshold_sensitivity() -> None:
    """Verify that small orders are not flagged as spoofing."""
    detector = SpoofingDetector()
    # High threshold means O1 (1000) should be ignored
    high_threshold = 5000
    flags = detector.detect_spoofing(TEST_EVENTS, large_order_vol=high_threshold)

    assert flags.is_empty()


def test_spoofing_empty_robustness() -> None:
    """Verify robustness to empty event streams."""
    detector = SpoofingDetector()
    empty = pl.DataFrame()
    res = detector.detect_spoofing(empty)
    assert res.is_empty()
