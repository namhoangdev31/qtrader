import polars as pl
from qtrader.validation.feature_validator import FeatureValidator

# Create the validator
validator = FeatureValidator(
    ic_lookback=2,
    ic_threshold=0.01,
    decay_threshold=0.5,
    stability_lookback=4
)

# Create two features: one good, one bad
good_feature = pl.Series("good", [1.0, 2.0, 3.0, 4.0, 5.0])
bad_feature = pl.Series("bad", [1.0, 1.0, 1.0, 1.0, 1.0])  # Constant
forward_returns = pl.Series("returns", [0.1, 0.2, 0.3, 0.4, 0.5])

print("Good feature:", good_feature)
print("Bad feature:", bad_feature)
print("Forward returns:", forward_returns)

# Validate both features
result = validator.validate({
    "good": good_feature,
    "bad": bad_feature
}, forward_returns)

print("Result:", result)
print("Result['good']:", result["good"])
print("Result['bad']:", result["bad"])

print("Good feature equal?", result["good"].equals(good_feature))
print("Bad feature sum:", result["bad"].sum())

# Check metrics for both
metrics = validator.get_metrics()
print("Metrics:", metrics)