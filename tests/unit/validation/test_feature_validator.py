import pytest
import polars as pl
from qtrader.validation.feature_validator import FeatureValidator

def test_feature_validator_initialization():
    # Valid initialization
    validator = FeatureValidator(ic_lookback=20, ic_threshold=0.02, decay_threshold=0.5, stability_lookback=60)
    assert validator.ic_lookback == 20
    assert validator.ic_threshold == 0.02
    assert validator.decay_threshold == 0.5
    assert validator.stability_lookback == 60

    # Invalid initializations
    with pytest.raises(ValueError, match="ic_lookback must be positive"):
        FeatureValidator(ic_lookback=0)
        
    with pytest.raises(ValueError, match="ic_threshold must be non-negative"):
        FeatureValidator(ic_threshold=-0.01)
        
    with pytest.raises(ValueError, match="decay_threshold must be non-negative"):
        FeatureValidator(decay_threshold=-0.1)
        
    with pytest.raises(ValueError, match="stability_lookback must be positive"):
        FeatureValidator(stability_lookback=-1)

def test_feature_validator_empty_features():
    validator = FeatureValidator()
    forward_returns = pl.Series("returns", [0.01, -0.01, 0.02])
    validated = validator.validate({}, forward_returns)
    assert validated == {}
    assert validator.get_metrics() == {}

def test_compute_ic_series():
    validator = FeatureValidator(ic_lookback=3)
    feature = pl.Series("feat", [1.0, 2.0, 3.0, 4.0, 5.0])
    returns = pl.Series("ret", [0.01, 0.02, 0.03, 0.01, 0.05])
    
    ic_series = validator._compute_ic_series(feature, returns)
    assert len(ic_series) == 5
    # First 2 should be 0 because lookback is 3
    assert ic_series[0] == 0.0
    assert ic_series[1] == 0.0
    # Values from index 2 onwards should be computed
    assert ic_series[2] is not None

def test_compute_decay_rate_empty_or_short():
    validator = FeatureValidator()
    assert validator._compute_decay_rate(pl.Series([])) == 0.0
    assert validator._compute_decay_rate(pl.Series([1.0])) == 0.0

def test_compute_decay_rate():
    validator = FeatureValidator()
    # Decreasing IC over time
    ic_series = pl.Series("ic", [0.5, 0.4, 0.3, 0.2, 0.1])
    decay = validator._compute_decay_rate(ic_series)
    assert decay < 0.0

def test_compute_stability_score_empty_or_short():
    validator = FeatureValidator()
    assert validator._compute_stability_score(pl.Series([])) == 0.0
    assert validator._compute_stability_score(pl.Series([1.0])) == 0.0

def test_compute_stability_score():
    validator = FeatureValidator()
    # Highly autocorrelated series
    ic_series = pl.Series("ic", [0.1, 0.11, 0.12, 0.11, 0.1, 0.09, 0.1])
    stability = validator._compute_stability_score(ic_series)
    assert isinstance(stability, float)

def test_validate_features_valid():
    validator = FeatureValidator(ic_lookback=2)
    # Give a feature that perfectly correlates with returns = High IC, no decay, high stability
    feature = pl.Series("feat", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    forward_returns = pl.Series("returns", [0.01, 0.02, 0.03, 0.04, 0.05, 0.06])
    
    features = {"good_feat": feature}
    validated = validator.validate(features, forward_returns)
    
    # Feature should remain intact
    assert "good_feat" in validated
    assert validated["good_feat"].to_list() == feature.to_list()
    
    metrics = validator.get_metrics()
    assert "good_feat" in metrics
    assert metrics["good_feat"]["ic_mean"] > validator.ic_threshold

def test_validate_features_invalid():
    # Set high thresholds so feature becomes invalid
    validator = FeatureValidator(ic_lookback=2, ic_threshold=0.99)
    # Feature with no correlation or weak correlation
    feature = pl.Series("feat", [1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    forward_returns = pl.Series("returns", [0.01, 0.02, 0.01, 0.02, 0.01, 0.02])
    
    features = {"bad_feat": feature}
    validated = validator.validate(features, forward_returns)
    
    # Feature should be zeroed out
    assert "bad_feat" in validated
    assert all(val == 0.0 for val in validated["bad_feat"].to_list())
    
    metrics = validator.get_metrics()
    assert "bad_feat" in metrics
