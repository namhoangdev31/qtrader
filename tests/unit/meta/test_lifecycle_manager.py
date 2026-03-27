import pytest

from qtrader.meta.lifecycle_manager import LifecycleEvent, LifecycleState, MetaLifecycleManager


@pytest.fixture
def manager() -> MetaLifecycleManager:
    """Initialize MetaLifecycleManager with industrial state machine."""
    return MetaLifecycleManager()


def test_lifecycle_happy_path(manager: MetaLifecycleManager) -> None:
    """Verify that a strategy correctly transitions from RESEARCH to LIVE."""
    strategy_id = "S1"

    # 1. RESEARCH -> PAPER
    state = manager.transition(strategy_id, LifecycleState.RESEARCH, LifecycleEvent.VALIDATED)
    assert state == LifecycleState.PAPER  # noqa: S101

    # 2. PAPER -> SHADOW
    state = manager.transition(strategy_id, LifecycleState.PAPER, LifecycleEvent.BACKTEST_PASS)
    assert state == LifecycleState.SHADOW  # noqa: S101

    # 3. SHADOW -> LIVE
    state = manager.transition(strategy_id, LifecycleState.SHADOW, LifecycleEvent.SHADOW_PASS)
    assert state == LifecycleState.LIVE  # noqa: S101


def test_lifecycle_jump_prevention(manager: MetaLifecycleManager) -> None:
    """Verify that skipping states (e.g. RESEARCH -> LIVE) is forbidden."""
    strategy_id = "S2"

    # 1. RESEARCH + SHADOW_PASS (Invalid)
    state = manager.transition(strategy_id, LifecycleState.RESEARCH, LifecycleEvent.SHADOW_PASS)
    assert state == LifecycleState.RESEARCH  # noqa: S101


def test_lifecycle_global_kill(manager: MetaLifecycleManager) -> None:
    """Verify that a RISK_BREACH can KILL a strategy in any state."""
    strategy_id = "S3"

    # 1. RESEARCH -> KILLED
    state_r = manager.transition(strategy_id, LifecycleState.RESEARCH, LifecycleEvent.RISK_BREACH)
    assert state_r == LifecycleState.KILLED  # noqa: S101

    # 2. SHADOW -> KILLED
    state_s = manager.transition("S4", LifecycleState.SHADOW, LifecycleEvent.RISK_BREACH)
    assert state_s == LifecycleState.KILLED  # noqa: S101

    # 3. LIVE -> KILLED
    state_l = manager.transition("S5", LifecycleState.LIVE, LifecycleEvent.RISK_BREACH)
    assert state_l == LifecycleState.KILLED  # noqa: S101


def test_lifecycle_observability_report(manager: MetaLifecycleManager) -> None:
    """Verify the validity of the lifecycle distribution report."""
    manager.transition("S1", LifecycleState.RESEARCH, LifecycleEvent.VALIDATED)  # PAPER
    manager.transition("S2", LifecycleState.RESEARCH, LifecycleEvent.RISK_BREACH)  # KILLED

    report = manager.get_observability_report()
    assert report["total_tracked"] == 2  # noqa: S101, PLR2004
    assert report["state_distribution"]["PAPER"] == 1  # noqa: S101
    assert report["state_distribution"]["KILLED"] == 1  # noqa: S101
