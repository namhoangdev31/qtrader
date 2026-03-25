import numpy as np
import polars as pl
import pytest

from qtrader.ml.online_learning import OnlineLearner

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SEED = 42
N_SAMPLES = 100
BATCH_SIZE = 10
N_FEATURES = 2
ETA_0 = 0.01
POWER_T = 0.25
SIGNAL_VAL = 2.0
ITERATIONS = 50
EXPECTED_LEN_2 = 2
EXPECTED_NON_EMPTY = 0


def test_online_initialization() -> None:
    """Verify state before any updates."""
    learner = OnlineLearner(eta0=ETA_0, power_t=POWER_T, random_state=SEED)
    assert not learner._is_initialized
    assert learner.coefficients.size == EXPECTED_NON_EMPTY

    # Predict on zeroes should return zeroes
    x_test = np.zeros((1, N_FEATURES))
    pred = learner.predict(x_test)
    assert pred[0] == 0.0


def test_online_update_fit() -> None:
    """Verify that coefficients change after an update."""
    learner = OnlineLearner(eta0=ETA_0, power_t=POWER_T, random_state=SEED)
    rng = np.random.default_rng(SEED)

    x_batch = rng.standard_normal((BATCH_SIZE, N_FEATURES))
    y_batch = SIGNAL_VAL * x_batch[:, 0]

    learner.update(x_batch, y_batch)
    assert learner._is_initialized
    coeff = learner.coefficients
    assert coeff.size == N_FEATURES
    assert not np.array_equal(coeff, np.zeros(N_FEATURES))


def test_online_batch_mismatch() -> None:
    """Verify error on shape mismatch."""
    learner = OnlineLearner(eta0=ETA_0, power_t=POWER_T, random_state=SEED)
    x_batch = np.zeros((BATCH_SIZE, N_FEATURES))
    y_batch = np.zeros(BATCH_SIZE - 1)  # Mismatch

    with pytest.raises(ValueError, match="Batch size mismatch"):
        learner.update(x_batch, y_batch)


def test_online_convergence() -> None:
    """Verify that the model learns over many batches."""
    learner = OnlineLearner(eta0=ETA_0, power_t=POWER_T, random_state=SEED)
    rng = np.random.default_rng(SEED)

    # Targets: y = 2*f1 - 1*f2
    weights = np.array([2.0, -1.0])

    # Track error
    errors = []

    for _ in range(ITERATIONS):
        x_batch = rng.standard_normal((BATCH_SIZE, N_FEATURES))
        y_batch = x_batch @ weights

        # Pred before update
        pred_before = learner.predict(x_batch)
        error_before = np.mean((y_batch - pred_before) ** 2)
        errors.append(error_before)

        learner.update(x_batch, y_batch)

    # Final error should be much lower than initial error
    assert errors[-1] < errors[0]


def test_online_polars_compat() -> None:
    """Verify support for Polars inputs."""
    learner = OnlineLearner(eta0=ETA_0, power_t=POWER_T, random_state=SEED)
    x_df = pl.DataFrame({"f1": [1.0, 2.0], "f2": [0.0, 1.0]})
    y_sr = pl.Series("target", [2.0, 4.0])

    learner.update(x_df, y_sr)
    assert learner._is_initialized
    pred = learner.predict(x_df)
    assert pred.shape[0] == EXPECTED_LEN_2
