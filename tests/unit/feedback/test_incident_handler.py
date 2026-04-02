import pytest

from qtrader.feedback.incident_handler import IncidentAction, IncidentResponseEngine


@pytest.fixture
def engine() -> IncidentResponseEngine:
    """Initialize an IncidentResponseEngine for institutional resilience certification."""
    return IncidentResponseEngine()


def test_incident_anomaly_scoring_veracity(engine: IncidentResponseEngine) -> None:
    """Verify that failure intensity scoring reflects multi-factor system signals."""
    # Scenario: Risk 0.4. Exec Errors 0. Sys Failures 0.
    # Score = 0.4 * 0.5 + 0 + 0 = 0.2
    report = engine.evaluate_incident_state(risk_score=0.4, execution_errors=0, system_failures=0)

    assert report["metrology"]["composite_anomaly_score"] == 0.2
    assert report["status"] == "INCIDENT_NORMAL"


def test_incident_autonomous_gating_critical(engine: IncidentResponseEngine) -> None:
    """Verify that critical scores trigger the correct EMERGENCY_HALT action."""
    # Scenario: Risk 0.9. Exec Errors 10. Sys Failures 10.
    # Score = (0.5 * 0.9) + (0.3 * 1.0) + (0.2 * 1.0) = 0.45 + 0.3 + 0.2 = 0.95
    report = engine.evaluate_incident_state(risk_score=0.9, execution_errors=10, system_failures=10)

    assert report["metrology"]["composite_anomaly_score"] == 0.95
    assert report["response"]["triggered_action_category"] == IncidentAction.EMERGENCY_HALT.value


def test_incident_tiered_remediation_pause(engine: IncidentResponseEngine) -> None:
    """Verify that failure intensity triggers the PAUSE_STRATEGIES action."""
    # Scenario: Risk 0.8. Exec Errors 6. Sys Failures 5.
    # Score = (0.5 * 0.8) + (0.3 * 0.6) + (0.2 * 0.5) = 0.4 + 0.18 + 0.1 = 0.68
    # Wait, 0.68 >= 0.6 -> REDUCE. Let's make it higher for PAUSE (0.8 threshold).
    # Score = (0.5 * 0.9) + (0.3 * 1.0) + (0.2 * 0.5) = 0.45 + 0.3 + 0.1 = 0.85
    report = engine.evaluate_incident_state(risk_score=0.9, execution_errors=10, system_failures=5)

    assert report["response"]["triggered_action_category"] == IncidentAction.PAUSE_STRATEGIES.value


def test_incident_telemetry_tracking(engine: IncidentResponseEngine) -> None:
    """Verify situational awareness and forensic incident telemetry indexing."""
    engine.evaluate_incident_state(risk_score=1.0, execution_errors=10, system_failures=10)  # FAIL
    engine.evaluate_incident_state(risk_score=1.0, execution_errors=10, system_failures=10)  # FAIL

    stats = engine.get_incident_telemetry()
    assert stats["total_incidents_triggered"] == 2
    assert stats["last_incident_action"] == IncidentAction.EMERGENCY_HALT.value
