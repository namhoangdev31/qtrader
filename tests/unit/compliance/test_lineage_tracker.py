import pytest
from qtrader.compliance.lineage_tracker import LineageTracker


@pytest.fixture
def tracker() -> LineageTracker:
    return LineageTracker()


def test_lineage_forward_linking(tracker: LineageTracker) -> None:
    tracker.link(signal_id="S1", decision_id="D1")
    tracker.link(decision_id="D1", order_id="O1")
    chain = tracker.get_forensics("O1")
    assert chain["signal_id"] == "S1"
    assert chain["decision_id"] == "D1"
    assert chain["order_id"] == "O1"


def test_lineage_backward_forensics(tracker: LineageTracker) -> None:
    tracker.link(signal_id="ALPHA_TRIGGER_01", decision_id="PORTFOLIO_D1")
    tracker.link(decision_id="PORTFOLIO_D1", order_id="OMS_O1")
    tracker.link(order_id="OMS_O1", fill_id="EXECUTION_F1")
    trace = tracker.get_forensics("EXECUTION_F1")
    assert trace["signal_id"] == "ALPHA_TRIGGER_01"
    assert trace["order_id"] == "OMS_O1"


def test_lineage_completeness_verification(tracker: LineageTracker) -> None:
    tracker.link(signal_id="S2", decision_id="D2", order_id="O2", fill_id="F2")
    assert tracker.is_complete("F2") is False
    tracker.link(fill_id="F2", position_id="POS_S2")
    assert tracker.is_complete("F2") is True
    assert tracker.is_complete("S2") is True


def test_lineage_telemetry_reporting(tracker: LineageTracker) -> None:
    tracker.link(signal_id="A1", decision_id="D1")
    tracker.link(signal_id="A2", decision_id="D2")
    tracker.link(signal_id="A1", decision_id="D1", order_id="O1", fill_id="F1", position_id="P1")
    tracker.is_complete("A1")
    report = tracker.get_report()
    assert report["total_chains"] == 2
    assert report["complete_chains"] == 1
    assert report["status"] == "LINEAGE"


def test_lineage_non_existent_id(tracker: LineageTracker) -> None:
    trace = tracker.get_forensics("VOID_ID")
    assert trace["signal_id"] is None
    assert tracker.is_complete("VOID_ID") is False
