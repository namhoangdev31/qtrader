from __future__ import annotations

import itertools

import polars as pl


class InteractionGenerator:
    @staticmethod
    def generate(
        df: pl.DataFrame,
        columns: list[str],
        include_pairwise: bool = True,
        include_nonlinear: bool = True,
    ) -> pl.DataFrame:
        exprs = []
        if include_nonlinear:
            for col in columns:
                exprs.append((pl.col(col).abs() + 1.0).log().alias(f"{col}_log"))
                exprs.append(pl.col(col).abs().sqrt().alias(f"{col}_sqrt"))
        if include_pairwise:
            for c1, c2 in itertools.combinations(columns, 2):
                exprs.append((pl.col(c1) * pl.col(c2)).alias(f"{c1}_x_{c2}"))
                epsilon = 1e-09
                exprs.append((pl.col(c1) / (pl.col(c2) + epsilon)).alias(f"{c1}_div_{c2}"))
        expanded_df = df.with_columns(exprs)
        return InteractionGenerator._clean_dataframe(expanded_df)

    @staticmethod
    def _clean_dataframe(df: pl.DataFrame) -> pl.DataFrame:
        exprs = []
        for c in df.columns:
            if df[c].dtype.is_float():
                exprs.append(
                    pl.when(pl.col(c).is_infinite() | pl.col(c).is_nan() | pl.col(c).is_null())
                    .then(0.0)
                    .otherwise(pl.col(c))
                    .alias(c)
                )
            elif df[c].dtype.is_integer():
                exprs.append(pl.col(c).fill_null(0).alias(c))
            else:
                exprs.append(pl.col(c))
        return df.with_columns(exprs)
