import pytest

from qtrader.certification.failover_test import FailoverSimulator, FailureScenario


@pytest.fixture
def simulator() -> FailoverSimulator:
    """Initialize a FailoverSimulator for institutional resilience certification."""
    return FailoverSimulator(max_failover_latency_seconds=5.0)


def test_failover_simulator_successful_pass(simulator: FailoverSimulator) -> None:
    """Verify that a 2.3s failover transition results in a SUCCESS status."""
    report = simulator.simulate_failover(
        scenario=FailureScenario.PRIMARY_SERVER_DOWN,
        simulated_transition_ms=2300.0,
        data_integrity_verified=True,
    )

    assert report["result"] == "SUCCESS"  # noqa: S101
    assert report["metrics"]["failover_latency_s"] == 2.3  # noqa: S101, PLR2004
    assert report["metrics"]["availability_target_met"] is True  # noqa: S101


def test_failover_simulator_latency_threshold_fail(simulator: FailoverSimulator) -> None:
    """Verify that a transition exceeding 5s results in a FAIL status."""
    report = simulator.simulate_failover(
        scenario=FailureScenario.DATABASE_UNAVAILABLE,
        simulated_transition_ms=6500.0,  # Exceeds 5.0s
        data_integrity_verified=True,
    )

    assert report["result"] == "FAIL"  # noqa: S101
    assert report["metrics"]["availability_target_met"] is False  # noqa: S101


def test_failover_simulator_data_loss_fail(simulator: FailoverSimulator) -> None:
    """Verify that any state inconsistency during failover triggers a failure (Zero tolerance)."""
    report = simulator.simulate_failover(
        scenario=FailureScenario.NETWORK_PARTITION,
        simulated_transition_ms=1000.0,  # Valid latency
        data_integrity_verified=False,  # INCONSISTENCY (Data loss)
    )

    assert report["result"] == "FAIL"  # noqa: S101


def test_failover_simulator_resilience_telemetry(simulator: FailoverSimulator) -> None:
    """Verify situational awareness and cumulative downtime tracking."""
    simulator.simulate_failover(FailureScenario.PRIMARY_SERVER_DOWN, simulated_transition_ms=500.0)
    # Testing both naming variants for robust certification
    db_scenario = (
        FailureScenario.DB_UNAVAILABLE
        if hasattr(FailureScenario, "DB_UNAVAILABLE")
        else FailureScenario.DATABASE_UNAVAILABLE
    )
    simulator.simulate_failover(db_scenario, simulated_transition_ms=1500.0)

    stats = simulator.get_resilience_telemetry()
    assert stats["total_failover_events"] == 2  # noqa: S101, PLR2004
    assert stats["cumulative_downtime_seconds"] == 2.0  # noqa: S101, PLR2004
    assert stats["status"] == "OPERATIONAL_RESILIENCE"  # noqa: S101


def test_failover_simulator_artifact_integrity(
    simulator: FailoverSimulator,
) -> None:
    """Verify that the failover artifact includes structural performance metadata."""
    report = simulator.simulate_failover(
        FailureScenario.NETWORK_PARTITION, simulated_transition_ms=100.0
    )

    assert "scenario" in report["certification"]  # noqa: S101
    assert report["certification"]["scenario"] == "NETWORK_PARTITION"  # noqa: S101
    assert "real_sim_duration_ms" in report["certification"]  # noqa: S101
