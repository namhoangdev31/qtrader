"""Unit tests for the OnlineMetaLearner."""
import numpy as np
import pytest

# Attempt to import the module. If torch is not available, we skip the tests.
try:
    from qtrader.ml.meta_online import OnlineMetaLearner
    # If we get here, the import succeeded.
    _import_success = True
except Exception as e:
    _import_success = False
    _import_error = e


@pytest.mark.skipif(not _import_success, reason=f"Failed to import OnlineMetaLearner: {_import_error}")
def test_update_returns_expected_keys():
    """Test that update returns a dictionary with the expected keys and types."""
    learner = OnlineMetaLearner()
    feedback = {
        "strategy_scores": {"strat1": 1.0},
        "feature_scores": {"feat1": 0.1},
        "risk_feedback": {"max_drawdown": 0.1},
    }
    state = learner.update(feedback, regime="regime1")
    assert "strategy_weights" in state
    assert "feature_weights" in state
    assert "risk_multiplier" in state
    assert isinstance(state["strategy_weights"], dict)
    assert isinstance(state["feature_weights"], dict)
    assert isinstance(state["risk_multiplier"], float)


@pytest.mark.skipif(not _import_success, reason=f"Failed to import OnlineMetaLearner: {_import_error}")
def test_update_does_not_crash():
    """Test that update can be called multiple times without crashing."""
    learner = OnlineMetaLearner()
    feedback = {
        "strategy_scores": {"strat1": 1.0, "strat2": 0.5},
        "feature_scores": {"feat1": 0.1, "feat2": 0.05},
        "risk_feedback": {"max_drawdown": 0.1},
    }
    # Call update multiple times
    for _ in range(5):
        state = learner.update(feedback, regime="regime1")
        # Just check that we get a state
        assert isinstance(state, dict)
        assert "strategy_weights" in state
        assert "feature_weights" in state
        assert "risk_multiplier" in state


if __name__ == "__main__":
    # If we are running the test file directly, run pytest on it.
    pytest.main([__file__])