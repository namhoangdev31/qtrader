import numpy as np
import pytest

from qtrader.alpha.signal_model import ProbabilisticSignalModel

# ──────────────────────────────────────────────
# Constants (PLR2004, N806)
# ──────────────────────────────────────────────
TEST_RANDOM_SEED = 42
EXPECTED_MU_UP_EDGE = 0.015
EXPECTED_MU_DOWN_EDGE = 0.05
NUM_TEST_SAMPLES = 2


def test_signal_model_fit_and_predict() -> None:
    """Verify that the model fits and predicts probabilities correctly."""
    model = ProbabilisticSignalModel(random_seed=TEST_RANDOM_SEED)

    # Synthetic data: x_matrix is correlated with y
    x_matrix = np.array([[1.0], [2.0], [3.0], [4.0], [5.0], [6.0]], dtype=np.float64)
    y = np.array([0, 0, 0, 1, 1, 1], dtype=np.float64)
    returns = np.array([-0.01, -0.02, -0.015, 0.02, 0.03, 0.025], dtype=np.float64)

    model.fit(x_matrix, y, returns)

    # Predict on test data
    x_test = np.array([[0.0], [7.0]], dtype=np.float64)
    probs = model.predict_proba(x_test)

    assert len(probs) == NUM_TEST_SAMPLES
    assert 0.0 <= probs[0] <= 1.0
    assert 0.0 <= probs[1] <= 1.0
    # Higher x_matrix should result in higher probability if positively correlated
    assert probs[1] > probs[0]


def test_expected_return() -> None:
    """Verify that expected return is calculated correctly."""
    model = ProbabilisticSignalModel(random_seed=TEST_RANDOM_SEED)
    x_matrix = np.array([[1.0], [2.0], [3.0], [4.0]], dtype=np.float64)
    y = np.array([0, 0, 1, 1], dtype=np.float64)
    returns = np.array([-0.01, -0.01, 0.02, 0.02], dtype=np.float64)

    model.fit(x_matrix, y, returns)

    # For x_matrix=2.5, probability should be around 0.5
    # For x_matrix=4.0, probability should be high
    expected_returns = model.compute_expected_return(x_matrix)

    assert len(expected_returns) == len(x_matrix)
    # High probability should correlate with higher expected return
    assert expected_returns[3] > expected_returns[0]


def test_trading_signal_thresholds() -> None:
    """Verify that buy/sell signals are generated based on thresholds."""
    model = ProbabilisticSignalModel(random_seed=TEST_RANDOM_SEED)
    x_matrix = np.array([[1.0], [2.0], [3.0], [4.0], [5.0], [6.0]], dtype=np.float64)
    y = np.array([0, 0, 0, 1, 1, 1], dtype=np.float64)
    returns = np.array([-0.01, -0.01, -0.01, 0.02, 0.02, 0.02], dtype=np.float64)

    model.fit(x_matrix, y, returns)

    # Use thresholds to isolate BUY/SELL/HOLD
    # Low x_matrix should be SELL, middle x_matrix HOLD, high x_matrix BUY
    signals = model.get_signal(x_matrix, theta_buy=0.8, theta_sell=0.2)

    assert signals[0] == -1  # Strongly low feature
    assert signals[5] == 1  # Strongly high feature
    assert signals[2] == -1 or signals[2] == 0  # Should not be BUY


def test_unfitted_model_raises_error() -> None:
    """Predicting with an unfitted model should raise RuntimeError."""
    model = ProbabilisticSignalModel()
    x_matrix = np.array([[1.0]], dtype=np.float64)

    with pytest.raises(RuntimeError, match="Model must be fitted"):
        model.predict_proba(x_matrix)


def test_edge_cases() -> None:
    """Verify edge cases like all up or all down moves."""
    model = ProbabilisticSignalModel()
    x_matrix = np.array([[1.0], [2.0], [-10.0]], dtype=np.float64)
    y = np.array([1, 1, 0], dtype=np.float64)
    returns = np.array([0.01, 0.02, -0.05], dtype=np.float64)

    # In some sklearn versions, fitting with only one class fails if no class balance
    # But for our test, let's at least check mu calculation
    model.fit(x_matrix, y, returns)
    assert model.mu_up == EXPECTED_MU_UP_EDGE
    assert model.mu_down == EXPECTED_MU_DOWN_EDGE
