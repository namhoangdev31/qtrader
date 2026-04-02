"""
Level 2 Critical Tests: Feature Base Contract
Covers: BaseFeature validate_inputs(), Feature Protocol compliance,
missing columns, below-min-periods, and statelessness.
"""
import polars as pl
import pytest

from qtrader.features.base import BaseFeature, Feature

# ---------------------------------------------------------------------------
# Concrete stub for testing BaseFeature mixin
# ---------------------------------------------------------------------------

class PriceReturnFeature(BaseFeature):
    name = "price_return"
    version = "1.0"
    required_cols = ["close"]
    min_periods = 2

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        close = df["close"]
        return (close / close.shift(1) - 1).rename(self.name)


class MultiColFeature(BaseFeature):
    name = "hl_spread"
    version = "1.0"
    required_cols = ["high", "low"]
    min_periods = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        self.validate_inputs(df)
        return (df["high"] - df["low"]).rename(self.name)


# ---------------------------------------------------------------------------
# validate_inputs()
# ---------------------------------------------------------------------------

def test_validate_missing_column_raises():
    f = PriceReturnFeature()
    df_no_close = pl.DataFrame({"open": [100.0, 101.0]})
    with pytest.raises(ValueError, match="Missing required columns"):
        f.validate_inputs(df_no_close)


def test_validate_below_min_periods_raises():
    f = PriceReturnFeature()  # min_periods = 2
    df_one_row = pl.DataFrame({"close": [100.0]})
    with pytest.raises(ValueError, match="Requires at least"):
        f.validate_inputs(df_one_row)


def test_validate_passes_exact_min_periods():
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 101.0]})   # exactly 2 rows
    f.validate_inputs(df)  # Must not raise


def test_validate_multi_col_missing_one():
    f = MultiColFeature()
    df = pl.DataFrame({"high": [1.0, 2.0]})  # missing "low"
    with pytest.raises(ValueError, match="low"):
        f.validate_inputs(df)


# ---------------------------------------------------------------------------
# compute() contract
# ---------------------------------------------------------------------------

def test_compute_output_length_matches_input():
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]})
    result = f.compute(df)
    assert result.len() == 5


def test_compute_first_row_is_null():
    """Return at index 0 is undefined (no prior row) → must be null."""
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 102.0, 104.0]})
    result = f.compute(df)
    assert result[0] is None


def test_compute_correctness():
    """100 → 110 → 121: returns should be 0.10, 0.10."""
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 110.0, 121.0]})
    result = f.compute(df)
    assert result[1] == pytest.approx(0.10, abs=1e-9)
    assert result[2] == pytest.approx(0.10, abs=1e-9)


def test_compute_stateless():
    """Two calls with the same input must return identical results."""
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 110.0, 105.0, 115.0]})
    r1 = f.compute(df)
    r2 = f.compute(df)
    assert r1.equals(r2)


def test_spread_feature_all_positive():
    f = MultiColFeature()
    df = pl.DataFrame({"high": [105.0, 106.0, 107.0], "low": [100.0, 101.0, 102.0]})
    result = f.compute(df)
    assert result.len() == 3
    assert all(v == pytest.approx(5.0) for v in result.to_list())


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------

def test_base_feature_satisfies_protocol():
    """BaseFeature (with concrete stub) must satisfy the Feature Protocol."""
    f: Feature = PriceReturnFeature()
    assert hasattr(f, "name")
    assert hasattr(f, "version")
    assert hasattr(f, "required_cols")
    assert hasattr(f, "min_periods")
    assert callable(f.compute)
    assert callable(f.validate_inputs)


def test_feature_name_is_output_series_name():
    f = PriceReturnFeature()
    df = pl.DataFrame({"close": [100.0, 110.0, 120.0]})
    result = f.compute(df)
    assert result.name == f.name, "Series name must equal feature.name"
