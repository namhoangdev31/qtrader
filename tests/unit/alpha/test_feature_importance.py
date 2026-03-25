import numpy as np
import polars as pl
from sklearn.linear_model import LinearRegression

from qtrader.alpha.feature_importance import FeatureImportance
from qtrader.alpha.models.gbdt_model import GBDTAlphaModel

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SEED = 42
N_SAMPLES = 100
N_FEATURES = 2
N_ESTIMATORS = 10
TOP_K = 1
SIGNAL_STRENGTH = 10.0
NOISE_STRENGTH = 0.1
EXPECTED_LEN_2 = 2
VAL_1 = 1


def test_importance_ranking() -> None:
    """Verify that the signal feature is ranked above the noise feature."""
    # Build data where f1 is the dominant signal
    rng = np.random.default_rng(SEED)
    f1 = rng.standard_normal(N_SAMPLES)
    f2 = rng.standard_normal(N_SAMPLES)  # Noise

    # y = 10*f1 + noise
    y = SIGNAL_STRENGTH * f1 + rng.normal(0, NOISE_STRENGTH, N_SAMPLES)

    x_data = pl.DataFrame({"signal": f1, "noise": f2})

    # Train a model
    model = GBDTAlphaModel(n_estimators=N_ESTIMATORS, random_state=SEED)
    model.fit(x_data, y)

    # Analyze importance
    importance = FeatureImportance.compute_importance(model.model, x_data)

    # First element should be 'signal'
    assert importance[0][0] == "signal"
    # signal importance should be positive
    assert importance[0][1] > 0.0
    # second element should be 'noise'
    assert importance[1][0] == "noise"


def test_importance_format() -> None:
    """Verify output data structures."""
    x_data = np.array([[1.0, 0.0], [0.0, 1.0], [1.1, 0.1]])
    y = np.array([1.0, 0.0, 1.1])

    model = GBDTAlphaModel(n_estimators=VAL_1, random_state=SEED)
    model.fit(x_data, y)

    importance = FeatureImportance.compute_importance(
        model.model, x_data, feature_names=["f1", "f2"]
    )

    assert isinstance(importance, list)
    assert len(importance) == EXPECTED_LEN_2
    assert isinstance(importance[0], tuple)
    assert isinstance(importance[0][0], str)
    assert isinstance(importance[0][1], float)


def test_top_features() -> None:
    """Verify top feature extraction."""
    importance = [("f1", 0.9), ("f2", 0.5), ("f3", 0.1)]
    top = FeatureImportance.get_top_features(importance, top_k=EXPECTED_LEN_2)

    assert top == ["f1", "f2"]
    assert len(top) == EXPECTED_LEN_2


def test_default_feature_names() -> None:
    """Verify default name generation for numpy input."""
    x_data = np.zeros((N_SAMPLES, N_FEATURES))
    y = np.zeros(N_SAMPLES)

    model = GBDTAlphaModel(n_estimators=VAL_1, random_state=SEED)
    model.fit(x_data, y)

    importance = FeatureImportance.compute_importance(model.model, x_data)
    # Check names feature_0, feature_1...
    assert importance[0][0].startswith("feature_")


def test_importance_general_model() -> None:
    """Verify importance with a non-tree model (e.g. Linear Regression fallback)."""
    x_data = np.random.default_rng(SEED).standard_normal((N_SAMPLES, N_FEATURES))
    y = SIGNAL_STRENGTH * x_data[:, 0]

    lr = LinearRegression()
    lr.fit(x_data, y)

    # This should trigger the Exception branch or shap.Explainer
    importance = FeatureImportance.compute_importance(lr, x_data)
    assert importance[0][0] == "feature_0"
    assert importance[0][1] > 0.0
