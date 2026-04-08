import time

import pytest

from qtrader.audit.audit_storage import AuditStorageManager


@pytest.fixture
def manager() -> AuditStorageManager:
    """Initialize an AuditStorageManager for institutional permanence."""
    return AuditStorageManager()


def test_audit_storage_immutability_and_integrity(manager: AuditStorageManager) -> None:
    """Verify that records are stored with SHA-256 integrity and can be verified."""
    topic = "TRADE_EXECUTION"
    payload = {"trade_id": "T1", "price": 50000.0, "qty": 1.0}

    # 1. Store Record
    record_id = manager.append(topic, payload)

    # 2. Verify Integrity
    assert manager.verify_integrity(record_id) is True

    # 3. Quaternary Integrity: SHA-256 matches
    report = manager.query_range(topic, 0.0, 1e12)
    assert report[0]["record_id"] == record_id
    assert report[0]["payload"] == payload


def test_audit_storage_tamper_detection(manager: AuditStorageManager) -> None:
    """Verify that any modification to a stored record is detected (Forensic Alert)."""
    topic = "RISK_VIOLATION"
    payload = {"user": "trader_01", "limit_breached": 100}

    record_id = manager.append(topic, payload)

    # Simulate tampering (mocking the internal storage)
    # This represents a bit-flip or intentional data corruption.
    manager._storage[record_id].payload_json = '{"user": "trader_01", "limit_breached": 0}'

    # Re-compute should fail
    assert manager.verify_integrity(record_id) is False


def test_audit_storage_retention_expiry_enforcement(
    manager: AuditStorageManager,
) -> None:
    """Verify that records are NOT purged before the 5-year retention gate."""
    topic = "COMPLIANCE_OVERRIDE"
    payload = {"approver": "admin", "token": "SEC_123"}

    record_id = manager.append(topic, payload)

    # Attempt immediate maintenance: Should delete 0 records (within retention)
    deleted = manager.perform_retention_maintenance()
    assert deleted == 0
    assert record_id in manager._storage


def test_audit_storage_point_in_time_query(manager: AuditStorageManager) -> None:
    """Verify that forensic queries correctly filter by topic and temporal window."""
    topic = "SIGNAL"
    manager.append(topic, {"id": "S1"})
    time.sleep(0.01)
    mid_point = time.time()
    time.sleep(0.01)
    manager.append(topic, {"id": "S2"})

    # 1. Full Range
    all_signals = manager.query_range(topic, 0.0, time.time())
    assert len(all_signals) == 2

    # 2. Windowed Range (Signals after mid_point)
    late_signals = manager.query_range(topic, mid_point, time.time())
    assert len(late_signals) == 1
    assert late_signals[0]["payload"]["id"] == "S2"


def test_audit_storage_telemetry_reporting(manager: AuditStorageManager) -> None:
    """Verify quaternary situational awareness for institutional storage cycles."""
    manager.append("TOPIC_A", {"data": 1})
    manager.verify_integrity(next(iter(manager._storage.keys())))

    report = manager.get_audit_report()
    assert report["total_records"] == 1
    assert report["integrity_verifications"] == 1
    assert report["status"] == "STORED"
