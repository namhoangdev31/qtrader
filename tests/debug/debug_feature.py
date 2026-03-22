import polars as pl
from qtrader.validation.feature_validator import FeatureValidator

# Create the validator
validator = FeatureValidator(
    ic_lookback=3,  # Small lookback for test
    ic_threshold=0.01,
    decay_threshold=0.1,
    stability_lookback=5
)

# Create a feature that should have high IC with forward returns
# Feature: [1.0, 2.0, 3.0, 4.0, 5.0]
# Returns: [0.1, 0.2, 0.3, 0.4, 0.5] (perfect correlation)
feature = pl.Series("test_feature", [1.0, 2.0, 3.0, 4.0, 5.0])
forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5])

print("Original feature:", feature)
print("Forward returns:", forward_returns)

# Validate the feature
result = validator.validate({"test_feature": feature}, forward_returns)

print("Result:", result)
print("Result['test_feature']:", result["test_feature"])
print("Are they equal?", result["test_feature"].equals(feature))
print("Values equal?", result["test_feature"].to_list() == feature.to_list())
print("Dtypes:", result["test_feature"].dtype, feature.dtype)
print("Names:", result["test_feature"].name, feature.name)

# Check metrics
metrics = validator.get_metrics()
print("Metrics:", metrics)