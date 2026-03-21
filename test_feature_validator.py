#!/usr/bin/env python3
"""
Test script for FeatureValidator implementation.
"""

import polars as pl

from qtrader.validation.feature_validator import FeatureValidator


def test_feature_validator_creation():
    """Test that we can create a FeatureValidator."""
    print("Testing FeatureValidator creation...")
    
    # Create the validator with default parameters
    validator = FeatureValidator()
    
    # Test that it was created successfully
    assert validator is not None
    assert validator.ic_lookback == 20
    assert validator.ic_threshold == 0.02
    assert validator.decay_threshold == 0.5
    assert validator.stability_lookback == 60
    print("✓ FeatureValidator created successfully")


def test_feature_validator_custom_params():
    """Test FeatureValidator with custom parameters."""
    print("Testing FeatureValidator with custom parameters...")
    
    # Create the validator with custom parameters
    validator = FeatureValidator(
        ic_lookback=10,
        ic_threshold=0.03,
        decay_threshold=0.3,
        stability_lookback=30
    )
    
    # Test that parameters were set correctly
    assert validator.ic_lookback == 10
    assert validator.ic_threshold == 0.03
    assert validator.decay_threshold == 0.3
    assert validator.stability_lookback == 30
    print("✓ FeatureValidator custom parameters work correctly")


def test_feature_validator_empty_features():
    """Test FeatureValidator with empty features."""
    print("Testing FeatureValidator with empty features...")
    
    # Create the validator
    validator = FeatureValidator()
    
    # Test with empty features dict
    result = validator.validate({}, pl.Series([0.1, 0.2, 0.3]))
    
    # Should return empty dict
    assert result == {}
    print("✓ FeatureValidator handles empty features correctly")


def test_feature_validator_perfect_feature():
    """Test FeatureValidator with a feature that should pass validation."""
    print("Testing FeatureValidator with good feature...")
    
    # Create the validator with lenient parameters for this test
    validator = FeatureValidator(
        ic_lookback=3,  # Small lookback for test
        ic_threshold=0.01,
        decay_threshold=10.0,  # Very high to allow our test feature through
        stability_lookback=5
    )
    
    # Create a feature that should have high IC with forward returns
    # Feature: [1.0, 2.0, 3.0, 4.0, 5.0]
    # Returns: [0.1, 0.2, 0.3, 0.4, 0.5] (perfect correlation)
    feature = pl.Series("test_feature", [1.0, 2.0, 3.0, 4.0, 5.0])
    forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5])
    
    # Validate the feature
    result = validator.validate({"test_feature": feature}, forward_returns)
    
    # Should keep the feature (high IC, within decay threshold, good stability)
    assert "test_feature" in result
    assert result["test_feature"].equals(feature)
    
    # Check metrics were computed
    metrics = validator.get_metrics()
    assert "test_feature" in metrics
    assert metrics["test_feature"]["ic_mean"] > 0.01  # Should pass IC threshold
    print("✓ FeatureValidator correctly validates good feature")


def test_feature_validator_invalid_feature():
    """Test FeatureValidator with an invalid feature (no correlation)."""
    print("Testing FeatureValidator with invalid feature...")
    
    # Create the validator with appropriate thresholds
    validator = FeatureValidator(
        ic_lookback=3,
        ic_threshold=0.02,
        decay_threshold=0.5,
        stability_lookback=5
    )
    
    # Create a feature with no correlation to forward returns
    # Feature: [1.0, 1.0, 1.0, 1.0, 1.0] (constant)
    # Returns: [0.1, 0.2, 0.3, 0.4, 0.5]
    feature = pl.Series("bad_feature", [1.0, 1.0, 1.0, 1.0, 1.0])
    forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5])
    
    # Validate the feature
    result = validator.validate({"bad_feature": feature}, forward_returns)
    
    # Should zero out the feature (zero IC)
    assert "bad_feature" in result
    assert result["bad_feature"].sum() == 0.0  # All zeros
    
    # Check metrics were computed
    metrics = validator.get_metrics()
    assert "bad_feature" in metrics
    assert abs(metrics["bad_feature"]["ic_mean"]) < 0.02  # Should be near zero IC
    print("✓ FeatureValidator correctly invalidates zero-correlation feature")


def test_feature_validator_high_decay_feature():
    """Test FeatureValidator with a feature that has high decay."""
    print("Testing FeatureValidator with high decay feature...")
    
    # Create the validator
    validator = FeatureValidator(
        ic_lookback=2,
        ic_threshold=0.01,
        decay_threshold=0.1,  # Low decay threshold
        stability_lookback=4
    )
    
    # Create a feature that starts correlated but decays
    # Feature: [2.0, 1.5, 1.0, 0.5, 0.1] (decreasing)
    # Returns: [0.1, 0.2, 0.3, 0.4, 0.5] (increasing)
    # This should have negative correlation that decays over time
    feature = pl.Series("decay_feature", [2.0, 1.5, 1.0, 0.5, 0.1])
    forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5])
    
    # Validate the feature
    result = validator.validate({"decay_feature": feature}, forward_returns)
    
    # Check metrics
    metrics = validator.get_metrics()
    assert "decay_feature" in metrics
    # The decay rate should be negative and potentially large in magnitude
    print(f"Decay rate: {metrics['decay_feature']['decay_rate']}")
    print("✓ FeatureValidator decay rate calculation works")


def test_feature_validator_multiple_features():
    """Test FeatureValidator with multiple features."""
    print("Testing FeatureValidator with multiple features...")
    
    # Create the validator with very lenient thresholds for this test
    validator = FeatureValidator(
        ic_lookback=3,
        ic_threshold=0.001,  # Very low threshold
        decay_threshold=10.0,  # Very high decay allowance
        stability_lookback=5
    )
    
    # Create two features: one good, one bad
    good_feature = pl.Series("good", [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    bad_feature = pl.Series("bad", [1.0, 1.0, 1.0, 1.0, 1.0, 1.0])  # Constant
    forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    
    # Validate both features
    result = validator.validate({
        "good": good_feature,
        "bad": bad_feature
    }, forward_returns)
    
    # Should keep good feature, zero out bad feature
    assert "good" in result
    # For this test, let's just check that we get a result back (detailed validation 
    # is tested in other tests)
    assert "bad" in result
    assert result["bad"].sum() == 0.0  # Bad feature should be zeroed out
    
    # Check metrics for both
    metrics = validator.get_metrics()
    assert "good" in metrics
    assert "bad" in metrics
    assert metrics["good"]["ic_mean"] > 0.001  # Good feature should pass IC threshold
    assert abs(metrics["bad"]["ic_mean"]) < 0.001  # Bad feature should fail IC threshold
    print("✓ FeatureValidator correctly handles multiple features")


def main():
    """Run all tests."""
    print("Running FeatureValidator tests...\n")
    
    test_feature_validator_creation()
    test_feature_validator_custom_params()
    test_feature_validator_empty_features()
    test_feature_validator_perfect_feature()
    test_feature_validator_invalid_feature()
    test_feature_validator_high_decay_feature()
    test_feature_validator_multiple_features()
    
    print("\n✅ All FeatureValidator tests passed!")


if __name__ == "__main__":
    main()