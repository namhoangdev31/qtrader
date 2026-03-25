import math

import polars as pl
import pytest

from qtrader.features.interaction import InteractionGenerator

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
VAL_1 = 1.0
VAL_2 = 2.0
VAL_3 = 3.0
VAL_4 = 4.0
VAL_10 = 10.0
VAL_0 = 0.0
VAL_20 = 20.0
VAL_5 = 5.0
EXPECTED_NONLINEAR_ONLY_WIDTH = 6
EXPECTED_PAIRWISE_ONLY_WIDTH = 4
EXPECTED_FULL_EXPANSION_WIDTH = 8
INDEX_0 = 0
INDEX_3 = 3
CLEAN_RANGE = 3


def test_generate_nonlinear_only() -> None:
    """Verify nonlinear expansion (log, sqrt) only."""
    df = pl.DataFrame({"a": [VAL_1, VAL_2], "b": [VAL_3, VAL_4]})

    result = InteractionGenerator.generate(
        df, ["a", "b"], include_pairwise=False, include_nonlinear=True
    )

    # 2 original + 2 log + 2 sqrt = 6
    assert result.width == EXPECTED_NONLINEAR_ONLY_WIDTH
    assert "a_log" in result.columns
    assert "b_sqrt" in result.columns


def test_generate_pairwise_only() -> None:
    """Verify pairwise expansion (mult, div) only."""
    df = pl.DataFrame({"a": [VAL_10, VAL_2], "b": [VAL_2, VAL_4]})

    result = InteractionGenerator.generate(
        df, ["a", "b"], include_pairwise=True, include_nonlinear=False
    )

    # 2 original + 1 mult (a*b) + 1 div (a/b) = 4
    assert result.width == EXPECTED_PAIRWISE_ONLY_WIDTH
    assert "a_x_b" in result.columns
    assert "a_div_b" in result.columns

    # Check values
    assert result["a_x_b"][INDEX_0] == VAL_20
    assert pytest.approx(result["a_div_b"][INDEX_0]) == VAL_5


def test_generate_full_expansion() -> None:
    """Verify full expansion with both pairwise and nonlinear."""
    df = pl.DataFrame({"a": [VAL_1, VAL_2], "b": [VAL_3, VAL_4]})

    result = InteractionGenerator.generate(df, ["a", "b"])

    # 2 original + 2 log + 2 sqrt + 1 mult + 1 div = 8
    assert result.width == EXPECTED_FULL_EXPANSION_WIDTH


def test_generate_cleaning() -> None:
    """Verify that NaNs and Infs are replaced by 0.0."""
    df = pl.DataFrame({"a": [VAL_1, VAL_0], "b": [VAL_0, VAL_1]})

    # This will cause a divide by zero (a=1, b=0) - just ensuring it runs
    InteractionGenerator.generate(df, ["a", "b"], include_nonlinear=False)

    df_raw = pl.DataFrame({"a": [float("nan"), float("inf"), -float("inf"), VAL_1]})

    cleaned = InteractionGenerator._clean_dataframe(df_raw)
    for i in range(CLEAN_RANGE):
        assert cleaned["a"][i] == VAL_0
    assert cleaned["a"][INDEX_3] == VAL_1


def test_generate_integer_cleaning() -> None:
    """Verify cleaning for integer columns with nulls."""
    df = pl.DataFrame({"a": [1, None]}, schema={"a": pl.Int64})
    cleaned = InteractionGenerator._clean_dataframe(df)
    assert cleaned["a"][1] == 0
    assert cleaned["a"].dtype == pl.Int64


def test_generate_other_types_cleaning() -> None:
    """Verify that non-numeric columns are preserved."""
    df = pl.DataFrame({"a": ["test", "ignore"]})
    cleaned = InteractionGenerator._clean_dataframe(df)
    assert cleaned["a"][0] == "test"


def test_generate_nonlinear_math() -> None:
    """Verify log and sqrt math accuracy."""
    val_x = math.exp(VAL_1) - VAL_1
    df = pl.DataFrame({"a": [val_x, VAL_3]})

    result = InteractionGenerator.generate(df, ["a"], include_pairwise=False)
    assert pytest.approx(result["a_log"][INDEX_0]) == VAL_1
    assert pytest.approx(result["a_sqrt"][INDEX_0]) == math.sqrt(val_x)
