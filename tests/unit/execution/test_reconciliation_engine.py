"""Unit tests for reconciliation engine."""

from __future__ import annotations

import pytest

from qtrader.execution.reconciliation_engine import ReconciliationEngine


def test_reconciliation_ok_when_positions_match() -> None:
    """Test reconciliation returns OK when local and exchange positions match."""
    engine = ReconciliationEngine(tolerance=1e-8)
    local_positions = {"BTC": 1.0, "ETH": 10.0}
    exchange_positions = {"BTC": 1.0, "ETH": 10.0}

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "OK"
    assert result["symbol_diff"] == {"BTC": 0.0, "ETH": 0.0}
    assert result["total_abs_diff"] == 0.0


def test_reconciliation_mismatch_when_positions_differ() -> None:
    """Test reconciliation returns MISMATCH when positions differ."""
    engine = ReconciliationEngine(tolerance=1e-8)
    local_positions = {"BTC": 1.0}
    exchange_positions = {"BTC": 0.9}

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "MISMATCH"
    assert abs(result["symbol_diff"]["BTC"] - 0.1) < 1e-10
    assert abs(result["total_abs_diff"] - 0.1) < 1e-10


def test_reconciliation_mismatch_when_symbols_differ() -> None:
    """Test reconciliation returns MISMATCH when symbol sets differ."""
    engine = ReconciliationEngine(tolerance=1e-8)
    local_positions = {"BTC": 1.0, "ETH": 5.0}
    exchange_positions = {"BTC": 1.0, "LTC": 2.0}

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "MISMATCH"
    # ETH: 5.0 - 0.0 = 5.0, LTC: 0.0 - 2.0 = -2.0 -> abs sum = 7.0
    assert result["symbol_diff"] == {"BTC": 0.0, "ETH": 5.0, "LTC": -2.0}
    assert result["total_abs_diff"] == 7.0


def test_reconciliation_ok_when_within_tolerance() -> None:
    """Test reconciliation returns OK when difference is within tolerance."""
    engine = ReconciliationEngine(tolerance=0.01)
    local_positions = {"BTC": 1.0}
    exchange_positions = {"BTC": 1.005}  # diff = 0.005 < 0.01

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "OK"
    assert abs(result["symbol_diff"]["BTC"] - (-0.005)) < 1e-10
    assert abs(result["total_abs_diff"] - 0.005) < 1e-10


def test_reconciliation_empty_positions() -> None:
    """Test reconciliation with empty position dictionaries."""
    engine = ReconciliationEngine(tolerance=1e-8)
    local_positions: dict[str, float] = {}
    exchange_positions: dict[str, float] = {}

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "OK"
    assert result["symbol_diff"] == {}
    assert result["total_abs_diff"] == 0.0


def test_reconciliation_zero_positions() -> None:
    """Test reconciliation with zero positions."""
    engine = ReconciliationEngine(tolerance=1e-8)
    local_positions = {"BTC": 0.0}
    exchange_positions = {"BTC": 0.0}

    result = engine.reconcile(local_positions, exchange_positions)

    assert result["status"] == "OK"
    assert result["symbol_diff"] == {"BTC": 0.0}
    assert result["total_abs_diff"] == 0.0
