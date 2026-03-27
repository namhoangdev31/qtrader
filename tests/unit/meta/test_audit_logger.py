import json
import os
from unittest.mock import AsyncMock

import pytest

from qtrader.meta.audit_logger import MetaAuditLogger


@pytest.fixture
def log_path(tmp_path: str) -> str:
    """Temporary path for the JSONL audit log."""
    return str(os.path.join(tmp_path, "meta_audit.log"))


@pytest.fixture
def mock_store() -> AsyncMock:
    """Mock AuditStore implementation."""
    store = AsyncMock()
    store.append.return_value = True
    return store


@pytest.mark.asyncio
async def test_meta_audit_logging_integrity(log_path: str, mock_store: AsyncMock) -> None:
    """Verify that decisions are correctly logged to both DB and File."""
    logger = MetaAuditLogger(audit_store=mock_store, log_path=log_path)

    # Log a dummy decision
    metrics = {"sharpe": 2.5, "mdd": 0.05}
    await logger.log_decision(
        module="TestModule",
        action="STRATEGY_VALIDATION",
        entity_id="S123",
        decision="APPROVED",
        reason="Exceeds industrial benchmarks",
        metrics=metrics,
    )

    # 1. Verify DB persistence (mock)
    assert mock_store.append.called  # noqa: S101
    event = mock_store.append.call_args[0][0]
    assert event.payload.module == "TestModule"  # noqa: S101
    assert event.payload.metrics["sharpe"] == 2.5  # noqa: S101, PLR2004

    # 2. Verify File persistence (JSONL)
    assert os.path.exists(log_path)  # noqa: S101
    with open(log_path) as f:
        line = f.readline()
        record = json.loads(line)
        assert record["module"] == "TestModule"  # noqa: S101
        assert record["decision"] == "APPROVED"  # noqa: S101
        assert record["metrics"]["mdd"] == 0.05  # noqa: S101, PLR2004


@pytest.mark.asyncio
async def test_meta_audit_store_failure_resilience(log_path: str) -> None:
    """Verify that a DB failure does not block the local file audit."""
    # Mock store that fails
    mock_store_fail = AsyncMock()
    mock_store_fail.append.return_value = False

    logger = MetaAuditLogger(audit_store=mock_store_fail, log_path=log_path)

    # Log a decision
    await logger.log_decision(
        module="FailSafe",
        action="ERROR_TEST",
        entity_id="E001",
        decision="REJECTED",
        reason="Simulated failure",
    )

    # 1. Verify DB failure tracking
    report = logger.get_audit_report()
    assert report["store_failures"] == 1  # noqa: S101

    # 2. Verify local file still contains the record (Immutability)
    with open(log_path) as f:
        record = json.loads(f.readline())
        assert record["module"] == "FailSafe"  # noqa: S101


@pytest.mark.asyncio
async def test_meta_audit_report_validity(log_path: str) -> None:
    """Verify the validity of the audit system health report."""
    logger = MetaAuditLogger(log_path=log_path)
    await logger.log_decision("M", "A", "E", "D", "R")

    report = logger.get_audit_report()
    assert report["events_logged"] == 1  # noqa: S101
    assert report["log_file"] == log_path  # noqa: S101


@pytest.mark.asyncio
async def test_meta_audit_local_failure_handling(mock_store: AsyncMock) -> None:
    """Verify that a local write failure triggers a critical log but doesn't crash."""
    # Point to a directory that doesn't exist or isn't writable
    logger = MetaAuditLogger(audit_store=mock_store, log_path="/invalid/path/audit.log")

    # Should not raise, just log error internally
    await logger.log_decision("M", "A", "E", "D", "R")

    # DB should still have been attempted
    assert mock_store.append.called  # noqa: S101
