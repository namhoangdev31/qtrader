from __future__ import annotations

import polars as pl


class AltDataProcessor:
    """
    Alternative Data Integration Engine.

    Ingests and merges non-standard data sources (sentiment, volume anomalies,
    external macro feeds) with existing price-based feature sets.
    Ensures temporal alignment and signal normalization (z-scoring).

    Adheres to the KILO.AI Industrial Grade Protocol for zero-latency,
    event-driven data processing.
    """

    @staticmethod
    def align_and_merge(
        main_features: pl.DataFrame, alt_data: pl.DataFrame, on: str = "timestamp"
    ) -> pl.DataFrame:
        """
        Merge alternative data source with the main feature matrix.

        Args:
            main_features: Existing feature DataFrame (OHLCV + price factors).
            alt_data: Alternative data DataFrame to join with its own features.
            on: Temporal alignment column (default 'timestamp').

        Returns:
            Enriched DataFrame with left-joined alternative features.
        """
        if main_features.is_empty():
            return main_features

        # Ensure temporal alignment column exists in both
        if on not in main_features.columns or on not in alt_data.columns:
            return main_features

        # Ensure column types match for join (e.g. both are Datetime)
        if main_features[on].dtype != alt_data[on].dtype:
            alt_data = alt_data.with_columns(pl.col(on).cast(main_features[on].dtype))

        # Perform left join to preserve the main feature set's temporal index.
        # This prevents look-ahead bias if alt_data is sparse.
        merged = main_features.join(alt_data, on=on, how="left")

        # Fill missing values with neutral 0.0 for alternative signals.
        # This assumes alt-signals are meant to be z-scored centered at 0.
        new_cols = [c for c in alt_data.columns if c != on]
        return merged.with_columns([pl.col(c).fill_null(0.0) for c in new_cols])

    @staticmethod
    def normalize_signals(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
        """
        Normalize alternative signals using z-score standardization.

        Mathematical Model:
        z = (x - mean) / std

        Args:
            df: Enriched DataFrame containing the raw alt-data.
            columns: List of columns to normalize.

        Returns:
            DataFrame containing original and z-scored alternative features.
        """
        if not columns:
            return df

        exprs = []
        for col in columns:
            mean_val = pl.col(col).mean()
            std_val = pl.col(col).std()

            # Stability check: handle zero variance to avoid division by zero
            safe_std = pl.when(std_val == 0).then(1.0).otherwise(std_val)
            z_score = (pl.col(col) - mean_val) / safe_std

            exprs.append(z_score.alias(f"{col}_z"))

        return df.with_columns(exprs)

    @staticmethod
    def process_pipeline(
        features: pl.DataFrame, external_sources: list[pl.DataFrame]
    ) -> pl.DataFrame:
        """
        Automated pipeline to ingest and normalize multiple alt-data sources.

        Args:
            features: Current feature set (the base for the join).
            external_sources: List of external DataFrames containing alt-info.

        Returns:
            Final Enriched DataFrame with all alt-data merged and normalized.
        """
        if not external_sources:
            return features

        enriched = features
        for src in external_sources:
            enriched = AltDataProcessor.align_and_merge(enriched, src)

        # Identify only the new columns added from the alternative sources
        alt_cols = [c for c in enriched.columns if c not in features.columns]

        if alt_cols:
            enriched = AltDataProcessor.normalize_signals(enriched, alt_cols)

        return enriched
