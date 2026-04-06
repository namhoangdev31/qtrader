"""Tests for data/quality_gate.py — Standash §4.1."""

from __future__ import annotations

import time

import polars as pl
import pytest

from qtrader.data.quality_gate import DataQualityGate


class TestDataQualityGate:
    def test_check_outlier_zscore(self) -> None:
        # Values within 3 std of mean should pass
        series = pl.Series([100.0, 101.0, 99.0, 100.5])
        DataQualityGate.check_outlier(series, method="zscore", threshold=3.0)

    def test_check_outlier_rejects_extreme(self) -> None:
        series = pl.Series([100.0, 101.0, 99.0, 1000.0])  # Extreme outlier
        with pytest.raises(Exception):
            DataQualityGate.check_outlier(series, method="zscore", threshold=1.0)

    def test_check_stale_rejects_old_timestamp(self) -> None:
        old_ts = (time.time() * 1000) - 10000  # 10 seconds ago
        with pytest.raises(Exception):
            DataQualityGate.check_stale(old_ts, max_age_ms=5000)

    def test_check_stale_accepts_fresh_timestamp(self) -> None:
        fresh_ts = time.time() * 1000
        DataQualityGate.check_stale(fresh_ts, max_age_ms=5000)

    def test_check_trade_quote_mismatch_within_spread(self) -> None:
        valid, _reason = DataQualityGate.check_trade_quote_mismatch(
            trade_price=150.0, best_bid=149.9, best_ask=150.1
        )
        assert valid

    def test_check_trade_quote_mismatch_below_bid(self) -> None:
        # Trade price 100.0 vs mid 150.0 = 33% deviation > 10% max
        valid, reason = DataQualityGate.check_trade_quote_mismatch(
            trade_price=100.0, best_bid=149.9, best_ask=150.1
        )
        assert not valid
        assert "below bid" in reason.lower()

    def test_check_trade_quote_mismatch_above_ask(self) -> None:
        # Trade price 200.0 vs mid 150.0 = 33% deviation > 10% max
        valid, reason = DataQualityGate.check_trade_quote_mismatch(
            trade_price=200.0, best_bid=149.9, best_ask=150.1
        )
        assert not valid
        assert "above ask" in reason.lower()

    def test_check_trade_quote_mismatch_invalid_spread(self) -> None:
        valid, _reason = DataQualityGate.check_trade_quote_mismatch(
            trade_price=150.0, best_bid=0, best_ask=0
        )
        assert valid  # Skip check for invalid spread
