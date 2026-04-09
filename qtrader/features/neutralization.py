from __future__ import annotations
import logging
import polars as pl

__all__ = ["FactorNeutralizer"]
_LOG = logging.getLogger("qtrader.features.neutralization")


class FactorNeutralizer:
    @staticmethod
    def sector_neutralize(
        df: pl.DataFrame, factor_col: str, group_col: str = "sector"
    ) -> pl.Series:
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
        if factor_col not in df.columns:
            raise ValueError(f"factor_col '{factor_col}' not found in df.")
        demeaned = pl.col(factor_col) - pl.col(factor_col).mean()
        return df.select(demeaned.alias(f"{factor_col}_mkt_neutral"))[f"{factor_col}_mkt_neutral"]

    @staticmethod
    def winsorize(series: pl.Series, lower: float = 0.01, upper: float = 0.99) -> pl.Series:
        lo = series.quantile(lower, interpolation="linear")
        hi = series.quantile(upper, interpolation="linear")
        return series.clip(lo, hi)

    @staticmethod
    def zscore(series: pl.Series, window: int | None = None) -> pl.Series:
        name = series.name or "zscore"
        if window is None:
            mean = float(series.mean() or 0.0)
            std = float(series.std() or 0.0)
            if std == 0.0:
                return pl.Series(name, [0.0] * series.len())
            return ((series - mean) / std).alias(name)
        rolling_mean = series.rolling_mean(window)
        rolling_std = series.rolling_std(window)
        result = (
            pl.when(rolling_std == 0.0).then(None).otherwise((series - rolling_mean) / rolling_std)
        )
        return result.alias(f"{name}_zscore{window}")

    @staticmethod
    def rank_normalize(series: pl.Series) -> pl.Series:
        name = series.name or "ranked"
        n = series.len()
        if n == 0:
            return series.alias(name)
        ranked = series.rank(method="average")
        min_r = float(ranked.min() or 1.0)
        max_r = float(ranked.max() or float(n))
        denom = max_r - min_r
        if denom == 0.0:
            return pl.Series(name, [0.5] * n)
        return ((ranked - min_r) / denom).alias(name)

    @staticmethod
    def orthogonalize(df: pl.DataFrame, factor_cols: list[str]) -> pl.DataFrame:
        if not factor_cols:
            raise ValueError("factor_cols must not be empty.")
        missing = [c for c in factor_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Missing factor columns: {missing}")
        try:
            import numpy as np
            from sklearn.decomposition import PCA
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
            f"ortho_{c}": result[:, i].tolist() for (i, c) in enumerate(factor_cols)
        }
        return pl.DataFrame(cols)
