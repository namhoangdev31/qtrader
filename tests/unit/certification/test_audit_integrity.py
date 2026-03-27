import pytest

from qtrader.certification.audit_integrity import AuditIntegrityValidator


@pytest.fixture
def validator() -> AuditIntegrityValidator:
    """Initialize an AuditIntegrityValidator for institutional forensic certification."""
    return AuditIntegrityValidator()


def test_audit_integrity_pass(validator: AuditIntegrityValidator) -> None:
    """Verify that a complete, bit-perfect hash chain results in a PASS status."""
    # 3 expected events
    expected = [{"id": 0}, {"id": 1}, {"id": 2}]
    stored = [
        {"id": 0, "prev_hash": "ROOT", "hash": "H0"},
        {"id": 1, "prev_hash": "H0", "hash": "H1"},
        {"id": 2, "prev_hash": "H1", "hash": "H2"},
    ]

    report = validator.run_integrity_audit(expected, stored)

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["completeness_ratio"] == 1.0  # noqa: S101
    assert report["metrics"]["tamper_breach_detected"] is False  # noqa: S101


def test_audit_integrity_completeness_breach_fail(validator: AuditIntegrityValidator) -> None:
    """Verify that a missing log (C < 1) results in a FAIL status."""
    # 3 expected, 2 stored
    expected = [{"id": 0}, {"id": 1}, {"id": 2}]
    stored = [
        {"id": 0, "prev_hash": "ROOT", "hash": "H0"},
        {"id": 1, "prev_hash": "H0", "hash": "H1"},
    ]

    report = validator.run_integrity_audit(expected, stored)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["metrics"]["completeness_ratio"] == 0.666667  # noqa: S101, PLR2004
    assert report["metrics"]["missing_event_count"] == 1  # noqa: S101


def test_audit_integrity_tamper_detection_fail(validator: AuditIntegrityValidator) -> None:
    """Verify that a broken hash chain results in a FAIL status."""
    expected = [{"id": 0}, {"id": 1}]
    stored = [
        {"id": 0, "prev_hash": "ROOT", "hash": "H0"},
        {"id": 1, "prev_hash": "H_TAMPER", "hash": "H1"},  # Mismatch
    ]

    report = validator.run_integrity_audit(expected, stored)

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["metrics"]["tamper_breach_detected"] is True  # noqa: S101


def test_audit_integrity_audit_telemetry(validator: AuditIntegrityValidator) -> None:
    """Verify situational awareness and lifecycle integrity scoring."""
    # 1 Pass, 1 Fail (missing)
    validator.run_integrity_audit([{"id": 0}], [{"id": 0, "prev_hash": "ROOT", "hash": "H0"}])
    validator.run_integrity_audit([{"id": 1}], [])

    stats = validator.get_audit_telemetry()
    assert stats["cumulative_missing_logs"] == 1  # noqa: S101
    assert stats["lifecycle_integrity_score"] == 0.5  # noqa: S101, PLR2004
    assert stats["status"] == "AUDIT_GOVERNANCE"  # noqa: S101


def test_audit_integrity_empty_handling(validator: AuditIntegrityValidator) -> None:
    """Verify that zero events result in a PASS/1.0 score."""
    report = validator.run_integrity_audit([], [])

    assert report["result"] == "PASS"  # noqa: S101
    assert report["metrics"]["completeness_ratio"] == 1.0  # noqa: S101
