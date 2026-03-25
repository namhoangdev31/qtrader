import numpy as np
import polars as pl
import pytest

from qtrader.alpha.feature_selection import FeatureSelector


@pytest.fixture
def synthetic_data() -> pl.DataFrame:
    """Generate synthetic data with informative and noise features."""
    np.random.seed(42)
    n_rows = 500

    # Informative linear feature (high IC, stable)
    f1 = np.random.normal(0, 1, n_rows)
    target = 0.05 * f1 + np.random.normal(0, 0.01, n_rows)

    # Informative non-linear feature (captured by MI)
    f2 = np.random.normal(0, 1, n_rows)
    target += 0.02 * np.sin(f2)
    # Add noise to make it unstable? Or just random noise

    # Pure noise
    noise = np.random.normal(0, 1, n_rows)

    return pl.DataFrame(
        {"feature_linear": f1, "feature_nonlinear": f2, "feature_noise": noise, "target": target}
    )


def test_feature_selector_selects_informative(synthetic_data: pl.DataFrame) -> None:
    """Verify that informative features are selected over noise."""
    selector = FeatureSelector(
        ic_threshold=0.01, mi_threshold=0.005, stability_threshold=0.1, window=100
    )

    features = ["feature_linear", "feature_nonlinear", "feature_noise"]
    selected = selector.select_features(synthetic_data, features, "target", top_k=2)

    assert "feature_linear" in selected
    assert "feature_nonlinear" in selected
    assert "feature_noise" not in selected


def test_feature_selector_empty_data() -> None:
    """Verify graceful handling of empty inputs."""
    selector = FeatureSelector()
    assert selector.select_features(pl.DataFrame(), ["f1"], "target") == []
    assert selector.select_features(pl.DataFrame({"f1": [1.0]}), [], "target") == []


def test_feature_selector_stability_filter() -> None:
    """Verify that unstable features are filtered out."""
    np.random.seed(42)
    n_rows = 300

    # Feature that is only correlated in the first half
    f_unstable = np.random.normal(0, 1, n_rows)
    target = np.zeros(n_rows)
    target[:150] = 0.1 * f_unstable[:150]
    target[150:] = -0.1 * f_unstable[150:]  # Correlation flip

    df = pl.DataFrame({"f_unstable": f_unstable, "target": target})

    selector = FeatureSelector(ic_threshold=0.001, stability_threshold=0.01, window=50)
    selected = selector.select_features(df, ["f_unstable"], "target")

    assert "f_unstable" not in selected


def test_feature_selector_top_k(synthetic_data: pl.DataFrame) -> None:
    """Verify top_k constraint."""
    selector = FeatureSelector(ic_threshold=0.0, mi_threshold=0.0)
    features = ["feature_linear", "feature_nonlinear", "feature_noise"]
    selected = selector.select_features(synthetic_data, features, "target", top_k=1)

    assert len(selected) == 1
    # feature_linear should be top due to strong linear relationship
    assert selected[0] == "feature_linear"
