from __future__ import annotations

import itertools

import polars as pl


class InteractionGenerator:
    """
    Automated generator for higher-order feature interactions.
    Expands the feature space to capture non-obvious relationships.
    """

    @staticmethod
    def generate(
        df: pl.DataFrame,
        columns: list[str],
        include_pairwise: bool = True,
        include_nonlinear: bool = True,
    ) -> pl.DataFrame:
        """
        Expand the feature space of the given DataFrame.

        Args:
            df: Input DataFrame.
            columns: List of feature columns to expand.
            include_pairwise: Whether to include pairwise interactions (*, /).
            include_nonlinear: Whether to include nonlinear transforms (log, sqrt).

        Returns:
            DataFrame with original and expanded features.
        """
        exprs = []

        if include_nonlinear:
            for col in columns:
                # log(abs(x) + 1) for stability
                exprs.append((pl.col(col).abs() + 1.0).log().alias(f"{col}_log"))
                # sqrt(abs(x)) for stability
                exprs.append(pl.col(col).abs().sqrt().alias(f"{col}_sqrt"))

        if include_pairwise:
            for c1, c2 in itertools.combinations(columns, 2):
                # Multiplication
                exprs.append((pl.col(c1) * pl.col(c2)).alias(f"{c1}_x_{c2}"))
                # Division (stable with epsilon)
                epsilon = 1e-9
                exprs.append((pl.col(c1) / (pl.col(c2) + epsilon)).alias(f"{c1}_div_{c2}"))

        # Apply expansions
        expanded_df = df.with_columns(exprs)

        # Final cleaning: replace NaNs/Infs with 0
        return InteractionGenerator._clean_dataframe(expanded_df)

    @staticmethod
    def _clean_dataframe(df: pl.DataFrame) -> pl.DataFrame:
        """Replace all non-finite values (null, nan, inf) with 0.0."""
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
