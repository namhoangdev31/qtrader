from unittest.mock import patch

import pytest

from qtrader.certification.determinism_test import DeterminismValidator


@pytest.fixture
def validator() -> DeterminismValidator:
    """Initialize a DeterminismValidator for industrial certification."""
    return DeterminismValidator()


def test_determinism_validator_bit_perfect_reproducibility(
    validator: DeterminismValidator,
) -> None:
    """Verify that identical inputs and seeds produce identical artifacts."""
    dataset = [{"price": 100.5}, {"price": 200.75}]

    report = validator.validate_reproducibility(dataset, random_seed=42)

    assert report["consistent"] is True  # noqa: S101
    assert (  # noqa: S101
        report["metrics"]["Trial_1_Artifact"] == report["metrics"]["Trial_2_Artifact"]
    )


def test_determinism_validator_seed_dependency_detection(
    validator: DeterminismValidator,
) -> None:
    """Verify that identical trial cycles produce identical results."""
    dataset = [{"price": 1000.0}] * 10
    report = validator.validate_reproducibility(dataset, random_seed=12345)
    assert report["consistent"] is True  # noqa: S101


def test_determinism_validator_mismatch_escalation(
    validator: DeterminismValidator,
) -> None:
    """Verify situational awareness and escalation for logic discrepancies."""
    # We trigger a mismatch by mocking the output to differ across trial calls
    with patch("qtrader.certification.determinism_test.random.random") as m_rand:
        # First Run (Run 1): 0.1
        # Second Run (Run 2): 0.2 (Mismatch)
        m_rand.side_effect = [0.1, 0.2]
        report = validator.validate_reproducibility([{"price": 10.0}])

    assert report["consistent"] is False  # noqa: S101
    stats = validator.get_determinism_telemetry()
    assert stats["verification_cycle_count"] == 1  # noqa: S101
    assert stats["mismatch_detected"] is True  # noqa: S101


def test_determinism_validator_artifact_construction(
    validator: DeterminismValidator,
) -> None:
    """Verify that the certification artifact includes structural metadata."""
    report = validator.validate_reproducibility([{"price": 500.0}], random_seed=1)

    metrics = report["metrics"]["Trial_1_Artifact"]
    assert "terminal_pnl" in metrics  # noqa: S101
    assert "ordered_identifiers" in metrics  # noqa: S101
    assert (  # noqa: S101
        report["certification"]["verification_duration_ms"] >= 0.0
    )
