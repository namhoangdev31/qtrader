import polars as pl
import pytest

from qtrader.certification.data_integrity import DataIntegrityValidator


@pytest.fixture
def validator() -> DataIntegrityValidator:
    """Initialize a DataIntegrityValidator for institutional certification."""
    return DataIntegrityValidator()


def test_data_integrity_validator_strict_ordering_pass(validator: DataIntegrityValidator) -> None:
    """Verify that perfectly sequenced and sanity-compliant ticks result in a PASS status."""
    df = pl.DataFrame(
        {"timestamp": [1e9, 1.1e9, 1.2e9], "price": [100.0, 101.0, 102.0], "qty": [10.0, 15.0, 5.0]}
    )

    artifact = validator.validate_dataset(df)

    assert artifact["result"] == "PASS"
    assert artifact["checks"]["monotonic_ordering"] is True
    assert artifact["checks"]["duplicate_count"] == 0


def test_data_integrity_validator_temporal_violation_fail(
    validator: DataIntegrityValidator,
) -> None:
    """Verify that out-of-order or duplicate timestamps trigger a FAIL status."""
    # 1. Out of order
    df_out = pl.DataFrame(
        {
            "timestamp": [1.2e9, 1.1e9, 1.3e9],
            "price": [10.0, 20.0, 30.0],
            "qty": [1.0, 1.0, 1.0],
        }
    )

    artifact_out = validator.validate_dataset(df_out)
    assert artifact_out["result"] == "FAIL"
    assert artifact_out["checks"]["monotonic_ordering"] is False

    # 2. Duplicate timestamp (Not strictly increasing)
    df_dupe = pl.DataFrame(
        {
            "timestamp": [1e9, 1e9, 1.1e9],
            "price": [10.0, 15.0, 20.0],
            "qty": [1.0, 1.0, 1.0],
        }
    )

    artifact_dupe = validator.validate_dataset(df_dupe)
    assert artifact_dupe["result"] == "FAIL"
    assert artifact_dupe["checks"]["monotonic_ordering"] is False


def test_data_integrity_validator_duplicate_record_escalation(
    validator: DataIntegrityValidator,
) -> None:
    """Verify that bit-perfect duplicate records are identified and flagged."""
    # Row 0 and Row 1 are identical across all fields
    df = pl.DataFrame(
        {
            "timestamp": [1e9, 1e9, 1.1e9],
            "price": [100.0, 100.0, 101.0],
            "qty": [10.0, 10.0, 5.0],
        }
    )

    artifact = validator.validate_dataset(df)

    assert artifact["result"] == "FAIL"
    assert artifact["checks"]["duplicate_count"] == 2


def test_data_integrity_validator_value_corruption_gating(
    validator: DataIntegrityValidator,
) -> None:
    """Verify that negative prices or quantities are blocked by sanity sensors."""
    df = pl.DataFrame(
        {
            "timestamp": [1e9, 1.1e9],
            "price": [-45.0, 100.0],  # Negative price
            "qty": [10.0, -1.0],  # Negative qty
        }
    )

    artifact = validator.validate_dataset(df)

    assert artifact["result"] == "FAIL"
    assert artifact["checks"]["corruption_count"] == 2


def test_data_integrity_validator_sha256_fidelity_check(validator: DataIntegrityValidator) -> None:
    """Verify that cryptographic fingerprint variations trigger an integrity mismatch failure."""
    df = pl.DataFrame({"timestamp": [1e9], "price": [50.0], "qty": [1.0]})

    # 1. Correct hash pass
    current_hash = validator.validate_dataset(df)["checks"]["integrity_hash"]
    report_pass = validator.validate_dataset(df, expected_hash=current_hash)
    assert report_pass["checks"]["lineage_verified"] is True

    # 2. Incorrect hash fail
    report_fail = validator.validate_dataset(df, expected_hash="INCORRECT_HASH")
    assert report_fail["result"] == "FAIL"
    assert report_fail["checks"]["lineage_verified"] is False


def test_data_integrity_validator_telemetry_tracking(
    validator: DataIntegrityValidator,
) -> None:
    """Verify situational awareness for industrial dataset structural health."""
    df_valid = pl.DataFrame({"timestamp": [1e9], "price": [10.0], "qty": [1.0]})
    df_invalid = pl.DataFrame({"timestamp": [1e9, 0.9e9], "price": [10.0, 10.0], "qty": [1.0, 1.0]})

    validator.validate_dataset(df_valid)
    validator.validate_dataset(df_invalid)

    stats = validator.get_integrity_telemetry()
    assert (
        stats["total_records_analyzed"] == 3
    )
    assert (
        stats["anomalous_dataset_count"] == 1
    )
    assert stats["status"] == "DATA_HEALTH"


def test_data_integrity_validator_empty_dataset_handling(
    validator: DataIntegrityValidator,
) -> None:
    """Verify that empty datasets are handled gracefully by the veracity sensor."""
    df = pl.DataFrame({"timestamp": [], "price": [], "qty": []})

    artifact = validator.validate_dataset(df)

    assert artifact["status"] == "DATA_CHECK_EMPTY"
    assert artifact["result"] == "PASS"
