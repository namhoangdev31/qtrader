"""Unit tests for the DataQualityGate."""

from __future__ import annotations

import pytest
import time

import polars as pl
from qtrader.data.quality_gate import DataQualityGate, DataQualityError


def test_check_outlier_no_outliers() -> None:
    """Test that a series with no outliers passes."""
    series = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    # Should not raise
    DataQualityGate.check_outlier(series, threshold=2.0)


def test_check_outlier_with_outliers() -> None:
    """Test that a series with outliers raises DataQualityError."""
    series = pl.Series([1.0, 2.0, 3.0, 4.0, 100.0])  # 100 is an outlier
    with pytest.raises(DataQualityError):
        DataQualityGate.check_outlier(series, threshold=1.5)


def test_check_outlier_constant_series() -> None:
    """Test that a constant series (std=0) passes."""
    series = pl.Series([5.0, 5.0, 5.0, 5.0])
    # Should not raise
    DataQualityGate.check_outlier(series, threshold=2.0)


def test_check_outlier_empty_series() -> None:
    """Test that an empty series passes."""
    series = pl.Series([], dtype=pl.Float64)
    # Should not raise
    DataQualityGate.check_outlier(series, threshold=2.0)


def test_check_stale_fresh_data() -> None:
    """Test that fresh data passes the stale check."""
    # Current time in milliseconds
    import time

    current_time_ms = int(time.time() * 1000)
    # Should not raise
    DataQualityGate.check_stale(current_time_ms, max_age_ms=5000)


def test_check_stale_old_data() -> None:
    """Test that old data raises DataQualityError."""
    old_time_ms = int(time.time() * 1000) - 10000  # 10 seconds ago
    with pytest.raises(DataQualityError):
        DataQualityGate.check_stale(old_time_ms, max_age_ms=5000)


def test_check_cross_exchange_sane() -> None:
    """Test that sane prices pass."""
    prices = {"exchange1": 100.0, "exchange2": 100.1, "exchange3": 99.9}
    # Spread is about 0.2% of mean ~100 -> should pass with default 1% threshold
    DataQualityGate.check_cross_exchange_sanity(prices, max_spread_pct=0.01)


def test_check_cross_exchange_insane() -> None:
    """Test that insane prices raise DataQualityError."""
    prices = {"exchange1": 100.0, "exchange2": 102.0, "exchange3": 98.0}
    # Spread is 4% of mean ~100 -> should fail with default 1% threshold
    with pytest.raises(DataQualityError):
        DataQualityGate.check_cross_exchange_sanity(prices, max_spread_pct=0.01)


def test_check_cross_exchange_single_price() -> None:
    """Test that a single exchange price passes (no spread)."""
    prices = {"exchange1": 100.0}
    # Should not raise
    DataQualityGate.check_cross_exchange_sanity(prices, max_spread_pct=0.01)


def test_check_cross_exchange_zero_mean() -> None:
    """Test that zero mean with zero spread passes."""
    prices = {"exchange1": 0.0, "exchange2": 0.0}
    # Should not raise
    DataQualityGate.check_cross_exchange_sanity(prices, max_spread_pct=0.01)


def test_check_cross_exchange_zero_mean_nonzero_spread() -> None:
    """Test that zero mean with non-zero spread raises."""
    prices = {"exchange1": 0.0, "exchange2": 1.0}
    with pytest.raises(DataQualityError):
        DataQualityGate.check_cross_exchange_sanity(prices, max_spread_pct=0.01)


def test_check_sequence_gap_valid() -> None:
    """Test that a valid sequence ID passes."""
    # Should not raise
    DataQualityGate.check_sequence_gap(seq_id=10, last_seq_id=9)


def test_check_sequence_gap_gap() -> None:
    """Test that a gap in sequence ID raises."""
    with pytest.raises(DataQualityError):
        DataQualityGate.check_sequence_gap(seq_id=12, last_seq_id=9)


def test_check_sequence_gap_out_of_order() -> None:
    """Test that an out-of-order sequence ID raises."""
    with pytest.raises(DataQualityError):
        DataQualityGate.check_sequence_gap(seq_id=9, last_seq_id=10)
