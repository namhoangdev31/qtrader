import pytest

from qtrader.compliance.lineage_tracker import LineageTracker


@pytest.fixture
def tracker() -> LineageTracker:
    """Initialize a LineageTracker for institutional traceability."""
    return LineageTracker()


def test_lineage_forward_linking(tracker: LineageTracker) -> None:
    """Verify that fragmented lifecycle stages can be linked forward."""
    # 1. Start with Signal
    tracker.link(signal_id="S1", decision_id="D1")

    # 2. Add Decision -> Order (D1 is our link)
    tracker.link(decision_id="D1", order_id="O1")

    # Check Signal -> Order
    chain = tracker.get_forensics("O1")
    assert chain["signal_id"] == "S1"
    assert chain["decision_id"] == "D1"
    assert chain["order_id"] == "O1"


def test_lineage_backward_forensics(tracker: LineageTracker) -> None:
    """Verify that a Fill ID can retrieve its originating Signal ID."""
    # Link: Signal1 -> Decision1 -> Order1 -> Fill1
    tracker.link(signal_id="ALPHA_TRIGGER_01", decision_id="PORTFOLIO_D1")
    tracker.link(decision_id="PORTFOLIO_D1", order_id="OMS_O1")
    tracker.link(order_id="OMS_O1", fill_id="EXECUTION_F1")

    # Given Fill ID, find Signal ID
    trace = tracker.get_forensics("EXECUTION_F1")
    assert trace["signal_id"] == "ALPHA_TRIGGER_01"
    assert trace["order_id"] == "OMS_O1"


def test_lineage_completeness_verification(tracker: LineageTracker) -> None:
    """Verify that only full lifecycle chains are flagged as complete."""
    # 1. Incomplete chain (Missing Position ID)
    tracker.link(signal_id="S2", decision_id="D2", order_id="O2", fill_id="F2")
    assert tracker.is_complete("F2") is False

    # 2. Complete chain
    tracker.link(fill_id="F2", position_id="POS_S2")
    assert tracker.is_complete("F2") is True
    assert tracker.is_complete("S2") is True


def test_lineage_telemetry_reporting(tracker: LineageTracker) -> None:
    """Verify situational awareness for institutional traceability cycles."""
    # 1. Create two separate chains
    tracker.link(signal_id="A1", decision_id="D1")
    tracker.link(signal_id="A2", decision_id="D2")

    tracker.link(signal_id="A1", decision_id="D1", order_id="O1", fill_id="F1", position_id="P1")
    tracker.is_complete("A1")

    report = tracker.get_report()
    assert report["total_chains"] == 2
    assert report["complete_chains"] == 1
    assert report["status"] == "LINEAGE"


def test_lineage_non_existent_id(tracker: LineageTracker) -> None:
    """Verify that querying for a non-existent ID returns an empty structure."""
    trace = tracker.get_forensics("VOID_ID")
    assert trace["signal_id"] is None
    assert tracker.is_complete("VOID_ID") is False
