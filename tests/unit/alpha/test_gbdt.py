import numpy as np
import polars as pl

from qtrader.alpha.models.gbdt_model import GBDTAlphaModel

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SEED = 42
N_SAMPLES = 100
N_FEATURES = 2
N_ESTIMATORS = 10
LEARNING_RATE = 0.1
MAX_DEPTH = 3
NOISE_LEVEL = 0.01

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SEED = 42
N_SAMPLES = 100
N_FEATURES = 2
N_ESTIMATORS = 10
LEARNING_RATE = 0.1
MAX_DEPTH = 3
NOISE_LEVEL = 0.01
LARGE_N_SAMPLES = 1000
LARGE_N_ESTIMATORS = 100
MAX_DEPTH_NONLINEAR = 5
MIN_IC_THRESHOLD = 0.8
MAX_MSE_THRESHOLD = 0.1
EXPECTED_LEN_5 = 5
VAL_2 = 2


def test_gbdt_deterministic() -> None:
    """Verify deterministic behavior with fixed seed."""
    x_data = np.random.default_rng(SEED).standard_normal((N_SAMPLES, N_FEATURES))
    y = x_data[:, 0] * x_data[:, 1]  # Nonlinear relationship

    model1 = GBDTAlphaModel(n_estimators=N_ESTIMATORS, random_state=SEED)
    model1.fit(x_data, y)
    pred1 = model1.predict(x_data)

    model2 = GBDTAlphaModel(n_estimators=N_ESTIMATORS, random_state=SEED)
    model2.fit(x_data, y)
    pred2 = model2.predict(x_data)

    np.testing.assert_array_almost_equal(pred1, pred2)


def test_gbdt_nonlinear_fit() -> None:
    """Verify that the model captures nonlinear interactions."""
    rng = np.random.default_rng(SEED)
    x_data = rng.standard_normal((LARGE_N_SAMPLES, N_FEATURES))
    # Target: product of features (highly nonlinear for linear models)
    y = x_data[:, 0] * x_data[:, 1] + rng.normal(0, NOISE_LEVEL, LARGE_N_SAMPLES)

    model = GBDTAlphaModel(
        n_estimators=LARGE_N_ESTIMATORS, max_depth=MAX_DEPTH_NONLINEAR, random_state=SEED
    )
    model.fit(x_data, y)

    metrics = model.evaluate(x_data, y)
    assert metrics["ic"] > MIN_IC_THRESHOLD
    assert metrics["mse"] < MAX_MSE_THRESHOLD


def test_gbdt_polars_compat() -> None:
    """Verify Polars DataFrame/Series support."""
    df = pl.DataFrame({"f1": [1.0, 2.0, 3.0, 4.0, 5.0], "f2": [0.5, 0.4, 0.3, 0.2, 0.1]})
    target = pl.Series("y", [1.1, 2.1, 3.1, 4.1, 5.1])

    model = GBDTAlphaModel(n_estimators=N_ESTIMATORS, random_state=SEED)
    model.fit(df, target)

    pred = model.predict(df)
    assert len(pred) == EXPECTED_LEN_5
    assert isinstance(pred, np.ndarray)


def test_gbdt_evaluate_format() -> None:
    """Verify evaluation metric dictionary format."""
    x_data = np.array([[1.0, 2.0], [3.0, 4.0]])
    y = np.array([1.5, 3.5])

    model = GBDTAlphaModel(n_estimators=VAL_2, random_state=SEED)
    model.fit(x_data, y)

    metrics = model.evaluate(x_data, y)
    assert "mse" in metrics
    assert "ic" in metrics
    assert isinstance(metrics["mse"], float)
    assert isinstance(metrics["ic"], float)
