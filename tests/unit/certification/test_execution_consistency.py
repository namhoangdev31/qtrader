import time
from typing import Any

import pytest

from qtrader.certification.execution_consistency import ExecutionConsistencyValidator


@pytest.fixture
def validator() -> ExecutionConsistencyValidator:
    """Initialize an ExecutionConsistencyValidator for institutional execution certification."""
    return ExecutionConsistencyValidator(size_epsilon=0.001, t_max_ms=1000.0)


def test_execution_consistency_alignment_pass(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify that a bit-perfect Signal -> Fill chain results in a PASS status."""
    now = time.time()
    signals = [{"lineage_id": "L1", "side": "BUY", "size": 10.0, "price": 100.0, "timestamp": now}]
    fills = [
        {
            "lineage_id": "L1",
            "side": "BUY",
            "size": 10.0,
            "price": 100.05,
            "timestamp": now + 0.5,
        }
    ]

    report = validator.validate_execution_lineage(signals, fills)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["signals_audited"] == 1  # noqa: S101
    assert report["metrics"]["average_slippage_impact"] == 0.05  # noqa: S101, PLR2004


def test_execution_consistency_size_mismatch_fail(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify that an underfill (size mismatch) exceeding 0.001 results in a FAIL status."""
    now = time.time()
    signals = [{"lineage_id": "L2", "side": "SELL", "size": 10.0, "price": 100.0, "timestamp": now}]
    fills = [
        {"lineage_id": "L2", "side": "SELL", "size": 9.0, "price": 99.95, "timestamp": now}
    ]  # 1.0 mismatch

    report = validator.validate_execution_lineage(signals, fills)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["lineage_audit"][0]["metrics"]["size_error"] == 1.0  # noqa: S101


def test_execution_consistency_timing_latency_fail(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify that a 2.0s fill latency exceeding 1.0s results in a FAIL status."""
    now = time.time()
    signals = [{"lineage_id": "L3", "side": "BUY", "size": 1.0, "price": 10.0, "timestamp": now}]
    fills = [
        {
            "lineage_id": "L3",
            "side": "BUY",
            "size": 1.0,
            "price": 10.0,
            "timestamp": now + 2.0,
        }
    ]

    report = validator.validate_execution_lineage(signals, fills)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["lineage_audit"][0]["metrics"]["latency_ms"] == 2000.0  # noqa: S101, PLR2004


def test_execution_consistency_side_dissonance_fail(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify that a side mismatch (BUY signal -> SELL fill) results in a structural failure."""
    now = time.time()
    signals = [{"lineage_id": "L4", "side": "BUY", "size": 1.0, "price": 10.0, "timestamp": now}]
    fills = [{"lineage_id": "L4", "side": "SELL", "size": 1.0, "price": 10.0, "timestamp": now}]

    report = validator.validate_execution_lineage(signals, fills)

    assert report["result"] == "FAIL"  # noqa: S101


def test_execution_consistency_governance_telemetry(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify situational awareness and cumulative mismatch rate tracking."""
    now = time.time()
    # Mocking multiple runs to update cumulative stats
    validator.validate_execution_lineage(
        [{"lineage_id": "T1", "side": "BUY", "size": 1.0, "price": 10, "timestamp": now}],
        [{"lineage_id": "T1", "side": "BUY", "size": 1.0, "price": 11, "timestamp": now}],
    )  # Pass
    validator.validate_execution_lineage(
        [{"lineage_id": "T2", "side": "BUY", "size": 1.0, "price": 10, "timestamp": now}],
        [{"lineage_id": "T2", "side": "SELL", "size": 1.0, "price": 10, "timestamp": now}],
    )  # Fail

    stats = validator.get_consistency_telemetry()
    assert stats["lifecycle_mismatch_rate"] == 50.0  # noqa: S101, PLR2004
    assert stats["total_slippage_drift"] == 0.5  # noqa: S101, PLR2004
    assert stats["status"] == "EXECUTION_GOVERNANCE"  # noqa: S101


def test_execution_consistency_orphan_and_missing_handling(
    validator: ExecutionConsistencyValidator,
) -> None:
    """Verify that orphan fills and missing signal-links are detected and reported."""
    now = time.time()
    # 1. Orphan Fill (Fill without Signal) - Warning case
    signals: list[dict[str, Any]] = []
    fills = [{"lineage_id": "ORPHAN", "side": "BUY", "size": 1.0, "price": 10, "timestamp": now}]
    report = validator.validate_execution_lineage(signals, fills)
    assert report["result"] == "PASS"  # noqa: S101

    # 2. Missing Link (Signal without Fill) - Failure case
    signals = [{"lineage_id": "MISSING", "side": "BUY", "size": 1.0, "price": 10, "timestamp": now}]
    fills = []
    report = validator.validate_execution_lineage(signals, fills)
    assert report["result"] == "FAIL"  # noqa: S101
    assert report["lineage_audit"][0]["violation"] == "LINEAGE_BREAK"  # noqa: S101
