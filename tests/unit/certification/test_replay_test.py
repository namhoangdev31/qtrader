import polars as pl
import pytest

from qtrader.certification.replay_test import SystemReplayValidator


@pytest.fixture
def validator() -> SystemReplayValidator:
    """Initialize a SystemReplayValidator for industrial certification."""
    return SystemReplayValidator(epsilon=1e-8)


def test_replay_validator_deterministic_pnl_pass(
    validator: SystemReplayValidator,
) -> None:
    """Verify that a successful end-to-end replay results in a PASS status."""
    df = pl.DataFrame({"timestamp": [1e9, 1.1e9, 1.2e9], "price": [10.0, 20.0, 30.0]})

    # Expected PnL: Sum(price * 0.001) = (10 + 20 + 30) * 0.001 = 0.06
    artifact = validator.run_certification(df, expected_pnl=0.06)

    assert artifact["result"] == "PASS"  # noqa: S101
    assert (  # noqa: S101
        artifact["metrics"]["Replayed_PnL"] == 0.06  # noqa: PLR2004
    )
    assert artifact["metrics"]["Tick_Count"] == 3  # noqa: S101, PLR2004


def test_replay_validator_fundamental_error_fail(
    validator: SystemReplayValidator,
) -> None:
    """Verify that a PnL discrepancy exceeding ε results in a FAIL status."""
    df = pl.DataFrame({"timestamp": [1e9], "price": [100.0]})

    # Expected PnL: (100 * 0.001) = 0.1
    # We provide expected_pnl = 0.2
    artifact = validator.run_certification(df, expected_pnl=0.2)

    assert artifact["result"] == "FAIL"  # noqa: S101
    assert artifact["metrics"]["PnL_Error"] == 0.1  # noqa: S101, PLR2004


def test_replay_validator_schema_violation_enforcement(
    validator: SystemReplayValidator,
) -> None:
    """Verify that datasets missing causal fields are programmatically blocked."""
    # Missing 'timestamp'
    invalid_df = pl.DataFrame({"price": [10.0]})

    with pytest.raises(ValueError, match="SCHEMA_VIOLATION"):
        validator.run_certification(invalid_df, expected_pnl=0.0)


def test_replay_validator_sequential_ingestion_determinism() -> None:
    """Verify that replaying identical data produces identical artifacts."""
    df = pl.DataFrame({"timestamp": [1e9, 1.1e9], "price": [50.0, 60.0]})

    # Fresh validators for determinism (no cumulative count interference)
    v1 = SystemReplayValidator()
    v2 = SystemReplayValidator()

    # PnL: (50 + 60) * 0.001 = 0.11
    report1 = v1.run_certification(df, expected_pnl=0.11)
    report2 = v2.run_certification(df, expected_pnl=0.11)

    # Structural values must be identical
    assert report1["metrics"] == report2["metrics"]  # noqa: S101
    assert report1["result"] == report2["result"]  # noqa: S101


def test_replay_validator_telemetry_tracking(
    validator: SystemReplayValidator,
) -> None:
    """Verify situational awareness for institutional certification throughput."""
    df = pl.DataFrame({"timestamp": [1e9], "price": [10.0]})
    # 1. Pass
    validator.run_certification(df, expected_pnl=0.01)
    # 2. Fail
    validator.run_certification(df, expected_pnl=0.5)

    stats = validator.get_certification_telemetry()
    assert stats["total_ticks"] == 2  # noqa: S101, PLR2004
    assert stats["mismatch_failures"] == 1  # noqa: S101
    assert stats["status"] == "CERTIFICATION"  # noqa: S101
