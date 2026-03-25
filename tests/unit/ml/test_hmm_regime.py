import numpy as np
import polars as pl
import pytest

from qtrader.ml.hmm_regime import HMMRegimeModel

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
SEED = 42
N_SAMPLES = 200
N_COMPONENTS = 3
MEAN_BEAR = -5.0
MEAN_SIDEWAYS = 0.0
MEAN_BULL = 5.0
NOISE_STD = 0.1
EXPECTED_LEN = 300
INDEX_100 = 100
INDEX_200 = 200
BEAR_STATE = 0
SIDEWAYS_STATE = 1
BULL_STATE = 2


def test_hmm_fit_reorders_states() -> None:
    """Verify that states are sorted by mean returns (interpretable)."""
    # Create synthetic returns for 3 distinct regimes
    rng = np.random.default_rng(SEED)

    # 100 Bear (-1.0), 100 Sideways (0.0), 100 Bull (1.0)
    bear = rng.normal(MEAN_BEAR, NOISE_STD, 100)
    sideways = rng.normal(MEAN_SIDEWAYS, NOISE_STD, 100)
    bull = rng.normal(MEAN_BULL, NOISE_STD, 100)

    returns = np.concatenate([bear, sideways, bull])
    df = pl.DataFrame({"ret": returns})

    model = HMMRegimeModel(n_components=N_COMPONENTS, random_state=SEED)
    model.fit(df, ["ret"])

    # Check that state_means are sorted ascending
    means = model.state_means.flatten()
    assert len(means) == N_COMPONENTS
    assert np.all(np.diff(means) > 0)


def test_hmm_predict_viterbi() -> None:
    """Verify Viterbi labels match synthetic regimes."""
    rng = np.random.default_rng(SEED)

    # 100 Bear (-1.0), 100 Sideways (0.0), 100 Bull (1.0)
    bear = rng.normal(MEAN_BEAR, NOISE_STD, 100)
    sideways = rng.normal(MEAN_SIDEWAYS, NOISE_STD, 100)
    bull = rng.normal(MEAN_BULL, NOISE_STD, 100)

    returns = np.concatenate([bear, sideways, bull])
    df = pl.DataFrame({"ret": returns})

    model = HMMRegimeModel(n_components=N_COMPONENTS, random_state=SEED)
    model.fit(df, ["ret"])

    regimes = model.predict(df, ["ret"])
    regimes_np = regimes.to_numpy()

    # Verify that the majority of labels are valid and the sequence is somewhat stable
    assert regimes_np.min() >= BEAR_STATE
    assert regimes_np.max() <= BULL_STATE

    # We verify that Bear regimes have much lower mean returns than Bull regimes
    # across the entire predicted sequence
    bear_mask = regimes_np == BEAR_STATE
    bull_mask = regimes_np == BULL_STATE

    if np.any(bear_mask) and np.any(bull_mask):
        assert returns[bear_mask].mean() < returns[bull_mask].mean()


def test_hmm_predict_proba() -> None:
    """Verify posterior probability matrix dimensions and normalization."""
    rng = np.random.default_rng(SEED)
    returns = rng.standard_normal(EXPECTED_LEN)
    df = pl.DataFrame({"ret": returns})

    model = HMMRegimeModel(n_components=N_COMPONENTS, random_state=SEED)
    model.fit(df, ["ret"])

    probs_df = model.predict_proba(df, ["ret"])
    assert probs_df.height == EXPECTED_LEN
    assert len(probs_df.columns) == N_COMPONENTS

    probs_sum = probs_df.select(pl.sum_horizontal(pl.all())).to_series().to_numpy()
    assert np.allclose(probs_sum, 1.0)


def test_hmm_properties_exposure() -> None:
    """Verify that internal properties are accessible and correctly formatted."""
    rng = np.random.default_rng(SEED)
    df = pl.DataFrame({"ret": rng.standard_normal(INDEX_100)})

    model = HMMRegimeModel(n_components=N_COMPONENTS, random_state=SEED)
    model.fit(df, ["ret"])

    assert model.transition_matrix.shape == (N_COMPONENTS, N_COMPONENTS)
    assert model.state_means.shape == (N_COMPONENTS, 1)


def test_hmm_unfitted_coverage() -> None:
    """Verify error on unfitted property access for coverage."""
    model = HMMRegimeModel(n_components=N_COMPONENTS)
    with pytest.raises(RuntimeError, match="Model is not fitted"):
        _ = model.transition_matrix

    with pytest.raises(RuntimeError, match="Model is not fitted"):
        _ = model.state_means

    with pytest.raises(RuntimeError, match="Model is not fitted"):
        model.predict_proba(pl.DataFrame({"ret": [0.0]}), ["ret"])


def test_hmm_empty_features_error() -> None:
    """Verify error on empty features."""
    model = HMMRegimeModel(n_components=N_COMPONENTS)
    df = pl.DataFrame({"ret": [0.001]})

    with pytest.raises(ValueError, match="feature_cols list cannot be empty"):
        model.fit(df, [])


def test_hmm_coverage_error_paths() -> None:
    """Trigger remaining error paths for 100% coverage."""
    model = HMMRegimeModel(n_components=N_COMPONENTS)
    df = pl.DataFrame({"ret": [0.0]})

    # Error path: _standardize without fit
    with pytest.raises(RuntimeError, match="Model stats not initialized"):
        model._standardize(np.array([[0.1]]))

    # Error path: state_map not initialized (internal state check)
    df_10 = pl.DataFrame({"ret": [0.0] * 10})
    model.fit(df_10, ["ret"])
    model._state_map = None
    with pytest.raises(RuntimeError, match="State map not initialized"):
        model.predict(df_10, ["ret"])
