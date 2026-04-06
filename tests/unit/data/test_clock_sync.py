"""Tests for data/clock_sync.py — Standash §4.10."""

from __future__ import annotations

import time

import pytest

from qtrader.data.clock_sync import ClockSynchronizer, ClockSyncResult


class TestClockSynchronizer:
    def test_check_drift_within_threshold(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        result = sync.check_drift(system_time_ms=1000000.0, exchange_time_ms=999999.5)
        assert result.drift_ms == 0.5
        assert result.is_within_threshold

    def test_check_drift_exceeds_threshold(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        result = sync.check_drift(system_time_ms=1000000.0, exchange_time_ms=999998.0)
        assert result.drift_ms == 2.0
        assert not result.is_within_threshold

    def test_check_drift_no_exchange_time(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        result = sync.check_drift(system_time_ms=1000000.0)
        assert result.drift_ms == 0.0
        assert result.is_within_threshold

    def test_correction_offset(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        # Add some drift measurements
        for i in range(10):
            sync.check_drift(system_time_ms=1000000.0 + i, exchange_time_ms=1000000.0)

        offset = sync.get_correction_offset_ms()
        assert isinstance(offset, float)

    def test_correct_timestamp(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        # Add drift measurements
        for _i in range(10):
            sync.check_drift(system_time_ms=1000000.0 + 2.0, exchange_time_ms=1000000.0)

        corrected = sync.correct_timestamp(1000000.0)
        assert isinstance(corrected, float)

    def test_status(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        sync.check_drift(system_time_ms=1000000.0, exchange_time_ms=999999.5)
        status = sync.get_status()
        assert status["max_drift_ms"] == 1.0
        assert status["alert_count"] == 0

    def test_status_with_alerts(self) -> None:
        sync = ClockSynchronizer(max_drift_ms=1.0)
        sync.check_drift(system_time_ms=1000000.0, exchange_time_ms=999995.0)  # 5ms drift
        status = sync.get_status()
        assert status["alert_count"] == 1
