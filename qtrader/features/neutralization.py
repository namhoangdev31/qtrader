"""Factor neutralization and signal transformation utilities.

All transforms use Polars expressions (.over(), .rank(), etc.).
No numpy loops, no Python row iteration.
"""

from __future__ import annotations

import logging

import polars as pl

__all__ = ["FactorNeutralizer"]

_LOG = logging.getLogger("qtrader.features.neutralization")


class FactorNeutralizer:
    """Neutralize and transform factors for signal quality.

    All methods are static — no state. Designed for use in both
    batch research pipelines and online feature transformation.
    """

    @staticmethod
    def sector_neutralize(
        df: pl.DataFrame,
        factor_col: str,
        group_col: str = "sector",
    ) -> pl.Series:
        """Z-score factor within each group (sector / exchange / regime).

        Uses Polars ``.over()`` for a single-pass group normalization —
        no Python loops or groupby-apply overhead.

        Args:
            df: Long-format DataFrame with ``factor_col`` and ``group_col``.
            factor_col: Column name of the factor to neutralize.
            group_col: Column to group by (default ``"sector"``).

        Returns:
            Group-neutralized Z-score series.
        """
        if factor_col not in df.columns:
            raise ValueError(f"factor_col '{factor_col}' not found in df.")
        if group_col not in df.columns:
            raise ValueError(f"group_col '{group_col}' not found in df.")

        mean_expr = pl.col(factor_col).mean().over(group_col)
        std_expr = pl.col(factor_col).std().over(group_col)
        neutralized = (
            pl.when(std_expr == 0.0)
            .then(0.0)
            .otherwise((pl.col(factor_col) - mean_expr) / std_expr)
        )
        return df.select(neutralized.alias(f"{factor_col}_sector_neutral"))[
            f"{factor_col}_sector_neutral"
        ]

    @staticmethod
    def market_neutralize(df: pl.DataFrame, factor_col: str) -> pl.Series:
        """Remove cross-sectional mean (market-level component).

        Equivalent to demeaning: residual = factor - mean(factor).
        This removes the market beta from the raw alpha signal.

        Args:
            df: DataFrame with ``factor_col``.
            factor_col: Column name of the factor.

        Returns:
            Market-demeaned series.
        """
        if factor_col not in df.columns:
            raise ValueError(f"factor_col '{factor_col}' not found in df.")
        demeaned = pl.col(factor_col) - pl.col(factor_col).mean()
        return df.select(demeaned.alias(f"{factor_col}_mkt_neutral"))[f"{factor_col}_mkt_neutral"]

    @staticmethod
    def winsorize(
        series: pl.Series,
        lower: float = 0.01,
        upper: float = 0.99,
    ) -> pl.Series:
        """Clip outliers at lower/upper quantiles.

        Essential before z-scoring: a single large outlier can dominate
        the entire distribution without winsorization.

        Args:
            series: Numeric input series.
            lower: Lower quantile clip bound (default 1st percentile).
            upper: Upper quantile clip bound (default 99th percentile).

        Returns:
            Winsorized series with same name as input.
        """
        lo = series.quantile(lower, interpolation="linear")
        hi = series.quantile(upper, interpolation="linear")
        return series.clip(lo, hi)

    @staticmethod
    def zscore(series: pl.Series, window: int | None = None) -> pl.Series:
        """Z-score normalization: cross-sectional (window=None) or rolling.

        Args:
            series: Numeric input series.
            window: If None, uses the global mean/std (cross-sectional).
                    If an integer, uses rolling window of that size.

        Returns:
            Z-scored series. Returns 0.0 where std == 0.
        """
        name = series.name or "zscore"
        if window is None:
            mean = float(series.mean() or 0.0)
            std = float(series.std() or 0.0)
            if std == 0.0:
                return pl.Series(name, [0.0] * series.len())
            return ((series - mean) / std).alias(name)

        # Rolling z-score via Polars expressions
        rolling_mean = series.rolling_mean(window)
        rolling_std = series.rolling_std(window)
        result = (
            pl.when(rolling_std == 0.0).then(None).otherwise((series - rolling_mean) / rolling_std)
        )
        return result.alias(f"{name}_zscore{window}")

    @staticmethod
    def rank_normalize(series: pl.Series) -> pl.Series:
        """Rank-transform to [0, 1] range.

        Most commonly used normalization at WorldQuant.
        Robust to outliers; preserves ordinal relationships.

        Args:
            series: Numeric input series.

        Returns:
            Rank-normalized series in [0, 1].
        """
        name = series.name or "ranked"
        n = series.len()
        if n == 0:
            return series.alias(name)
        ranked = series.rank(method="average")
        # Normalize to [0, 1]
        min_r = float(ranked.min() or 1.0)
        max_r = float(ranked.max() or float(n))
        denom = max_r - min_r
        if denom == 0.0:
            return pl.Series(name, [0.5] * n)
        return ((ranked - min_r) / denom).alias(name)

    @staticmethod
    def orthogonalize(
        df: pl.DataFrame,
        factor_cols: list[str],
    ) -> pl.DataFrame:
        """PCA-based factor orthogonalization.

        Removes collinearity between factors by projecting onto principal
        components. Each component is uncorrelated with others.

        Args:
            df: DataFrame with numeric factor columns.
            factor_cols: Column names of factors to orthogonalize.

        Returns:
            DataFrame with orthogonalized factor columns (same names,
            prefixed with ``ortho_``).
        """
        if not factor_cols:
            raise ValueError("factor_cols must not be empty.")
        missing = [c for c in factor_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing factor columns: {missing}")

        # Convert to numpy for PCA (sklearn/numpy), then return as Polars
        try:
            import numpy as np
            from sklearn.decomposition import PCA  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "orthogonalize requires scikit-learn: pip install scikit-learn"
            ) from exc

        mat = df.select(factor_cols).to_numpy()
        mask = ~np.isnan(mat).any(axis=1)
        result = np.full_like(mat, float("nan"))

        if mask.sum() >= 2:
            pca = PCA(n_components=len(factor_cols))
            components = pca.fit_transform(mat[mask])
            result[mask] = components

        cols: dict[str, list[float]] = {
            f"ortho_{c}": result[:, i].tolist() for i, c in enumerate(factor_cols)
        }
        return pl.DataFrame(cols)


"""
# Pytest-style unit tests:

def test_winsorize_clips_top_outlier() -> None:
    import polars as pl
    from qtrader.features.neutralization import FactorNeutralizer

    s = pl.Series("x", [1.0, 2.0, 3.0, 4.0, 1000.0])
    ws = FactorNeutralizer.winsorize(s, lower=0.0, upper=0.8)
    assert float(ws.max()) <= 4.0

def test_zscore_cross_sectional_mean_zero() -> None:
    import polars as pl
    from qtrader.features.neutralization import FactorNeutralizer

    s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    z = FactorNeutralizer.zscore(s)
    assert abs(float(z.mean())) < 1e-9

def test_rank_normalize_range() -> None:
    import polars as pl
    from qtrader.features.neutralization import FactorNeutralizer

    s = pl.Series([10.0, 20.0, 5.0, 40.0, 30.0])
    ranked = FactorNeutralizer.rank_normalize(s)
    assert float(ranked.min()) == 0.0
    assert float(ranked.max()) == 1.0
"""
