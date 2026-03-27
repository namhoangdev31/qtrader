import pytest

from qtrader.certification.go_live_gate import GoLiveCertificationGate


@pytest.fixture
def certification_gate() -> GoLiveCertificationGate:
    """Initialize a GoLiveCertificationGate for institutional deployment certification."""
    return GoLiveCertificationGate()


def test_go_live_gate_total_pass(certification_gate: GoLiveCertificationGate) -> None:
    """Verify that a 100% PASS result across all modules results in APPROVED status."""
    test_results = {
        "Risk": {"result": "PASS", "status": "RISK_VERIFIED"},
        "Capital": {"result": "PASS", "status": "SOLVENCY_VERIFIED"},
        "Latency": {"result": "PASS", "status": "SPEED_VERIFIED"},
    }

    report = certification_gate.evaluate_certification_readiness(test_results)

    assert report["result"] == "APPROVED"  # noqa: S101
    assert report["metrics"]["total_modules_audited"] == 3  # noqa: S101, PLR2004
    assert report["metrics"]["rejected_module_count"] == 0  # noqa: S101


def test_go_live_gate_single_failure_reject(certification_gate: GoLiveCertificationGate) -> None:
    """Verify that a single failed module triggers REJECTED status."""
    test_results = {
        "Risk": {"result": "PASS", "status": "RISK_VERIFIED"},
        "Capital": {"result": "FAIL", "status": "SOLVENCY_BREACH"},  # FAIL
        "Latency": {"result": "PASS", "status": "SPEED_VERIFIED"},
    }

    report = certification_gate.evaluate_certification_readiness(test_results)

    assert report["result"] == "REJECTED"  # noqa: S101
    assert len(report["rejection_forensics"]) == 1  # noqa: S101
    assert report["rejection_forensics"][0]["module"] == "Capital"  # noqa: S101
    assert report["rejection_forensics"][0]["reason"] == "SOLVENCY_BREACH"  # noqa: S101


def test_go_live_gate_fail_safe_empty(certification_gate: GoLiveCertificationGate) -> None:
    """Verify that an empty test result set triggers REJECTED status (Fail-Safe)."""
    # Act
    report = certification_gate.evaluate_certification_readiness({})

    # Assert
    assert report["result"] == "REJECTED"  # noqa: S101
    assert report["rejection_forensics"][0]["reason"] == "EMPTY_CERTIFICATION_SUITE"  # noqa: S101


def test_go_live_gate_telemetry_tracking(certification_gate: GoLiveCertificationGate) -> None:
    """Verify cumulative approval rate and failure module indexing."""
    # 1 Pass, 1 Fail
    certification_gate.evaluate_certification_readiness({"M1": {"result": "PASS"}})
    certification_gate.evaluate_certification_readiness({"M1": {"result": "FAIL"}})

    stats = certification_gate.get_certification_telemetry()
    assert stats["lifecycle_approval_rate"] == 0.5  # noqa: S101, PLR2004
    assert stats["total_rejections"] == 1  # noqa: S101
    assert stats["rejection_distribution_count"]["M1"] == 1  # noqa: S101
