# 08 — QUANT RESEARCH & FACTOR ENGINEERING

Standards for transforming raw features into alpha signals using factor models.

---

## 1. Feature Pre-processing (The Z-Score Rule)

ALL raw features must be standardized before being combined into factors.

- **Method**: Cross-sectional Z-score.
- **Implementation**: `(df[col] - df[col].mean()) / df[col].std()`
- **Grouping**: Always perform standardization within specific time buckets (e.g., per candle/timestamp) to avoid look-ahead bias and handle cross-sectional variance.

## 2. Factor Mathematical Constraints

- **Single Function/Method**: Each factor (e.g., Momentum, Mean Reversion) should be computed in its own method using vectorized Polars expressions.
- **No Scikit-Learn**: Vector operations must use `Polars`. No `sklearn.preprocessing` or `pandas`.
- **Handling Outliers**: Use Winsorization or clipping ONLY in the pre-alpha stage.

## 3. Factor Neutralization

Advanced factors must account for common risk exposures.

- **Beta Neutrality**: Ensure the factor signal has near-zero correlation with the market benchmark.
- **Sector/Asset Class Neutrality**: Group features by asset class and subtract the mean before final combination.

## 4. Weighted Combination

Composite Alpha signals are formed by combining normalized factors.

- **Standard**: Equal-weighted average of Z-scores.
- **Risk-Adjusted**: Inverse-volatility weighting at the factor level.

## 5. Verification Checklist

- [ ] Does `compute_factors()` use `.group_by("timestamp")` for cross-sectional normalization?
- [ ] Is every factor component a pure Polars expression?
- [ ] Are all factor scores between roughly [-3, 3] (Z-score range)?
- [ ] Has look-ahead bias been eliminated from the rolling calculations?
