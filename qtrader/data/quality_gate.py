"""Data quality gate for validating market data before alpha processing."""

from __future__ import annotations

import time

import polars as pl
from loguru import logger


class DataQualityError(Exception):
    """Exception raised when data quality checks fail."""

    pass


class DataQualityGate:
    """Gate for checking data quality of market data."""

    @staticmethod
    def check_outlier(series: pl.Series, method: str = "zscore", threshold: float = 3.0) -> None:
        """
        Check for outliers in a series using Z-score method.

        Args:
            series: Polars series of numeric values.
            method: Currently only "zscore" is supported.
            threshold: Z-score threshold above which a value is considered an outlier.

        Raises:
            DataQualityError: If any value in the series is an outlier.
        """
        if method != "zscore":
            raise ValueError(f"Unsupported method: {method}. Only 'zscore' is currently supported.")

        if series.is_empty():
            # No data to check
            return

        # Ensure we are working with a numeric series
        try:
            numeric_series = series.cast(pl.Float64)
        except Exception:
            raise ValueError(f"Series must be numeric, got {series.dtype}")

        if numeric_series.is_empty():
            # No data to check
            return

        # Compute mean and standard deviation
        mean = numeric_series.mean()
        std = numeric_series.std()

        # If all values are null, mean and std will be None
        if mean is None or std is None:
            # No valid data to check for outliers
            return

        # If std is zero, all values are identical -> no outliers
        if std == 0.0:
            return

        # Calculate Z-scores and check if any exceed the threshold
        z_scores = (numeric_series - mean) / std
        max_abs_z = z_scores.abs().max()

        # max_abs_z from Polars is already a scalar float for non-empty series
        # But let's handle the edge case where it might be None
        if max_abs_z is None:
            return

        # At this point, max_abs_z should be a float, but help mypy understand
        assert isinstance(max_abs_z, float), f"Expected float, got {type(max_abs_z)}"

        if max_abs_z > threshold:
            logger.error(
                f"Outlier detected in data series: max |z| = {max_abs_z:.4f}, "
                f"threshold = {threshold}, series length = {len(series)}"
            )
            raise DataQualityError(
                f"Outlier detected: max |z| = {max_abs_z:.4f} > threshold {threshold}"
            )

    @staticmethod
    def check_stale(ts: float, max_age_ms: int = 5000) -> None:
        """
        Check if a timestamp is stale (too old).

        Args:
            ts: Timestamp in milliseconds.
            max_age_ms: Maximum allowed age in milliseconds.

        Raises:
            DataQualityError: If the data is stale.
        """
        current_time_ms = int(time.time() * 1000)
        age_ms = current_time_ms - ts

        if age_ms > max_age_ms:
            logger.error(f"Stale data detected: age = {age_ms} ms > max_age = {max_age_ms} ms")
            raise DataQualityError(
                f"Stale data: age {age_ms} ms exceeds maximum allowed age {max_age_ms} ms"
            )

    @staticmethod
    def check_cross_exchange_sanity(prices: dict[str, float], max_spread_pct: float = 0.01) -> None:
        """
        Check sanity of prices across different exchanges.

        Args:
            prices: Dictionary mapping exchange name to price.
            max_spread_pct: Maximum allowed spread as a percentage of the mean price.

        Raises:
            DataQualityError: If the spread between exchanges is too large.
        """
        if not prices:
            # No prices to compare
            return

        prices_list = list(prices.values())
        max_price = max(prices_list)
        min_price = min(prices_list)
        mean_price = sum(prices_list) / len(prices_list)

        # Handle case where mean price is zero to avoid division by zero
        if mean_price == 0.0:
            if max_price != min_price:
                logger.error(f"Zero mean price with non-zero spread: prices = {prices}")
                raise DataQualityError(
                    f"Zero mean price but prices vary: min={min_price}, max={max_price}"
                )
            else:
                # All prices are zero, which is acceptable
                return

        spread_pct = (max_price - min_price) / mean_price

        if spread_pct > max_spread_pct:
            logger.error(
                f"Cross-exchange price spread too large: {spread_pct:.4f} > {max_spread_pct}"
            )
            raise DataQualityError(
                f"Price spread {spread_pct:.4f} exceeds maximum allowed {max_spread_pct}"
            )

    @staticmethod
    def check_sequence_gap(seq_id: int, last_seq_id: int) -> None:
        """
        Check for gaps or out-of-order sequence IDs.

        Args:
            seq_id: Current sequence ID.
            last_seq_id: Last seen sequence ID.

        Raises:
            DataQualityError: If there is a gap or the sequence is out of order.
        """
        expected_seq_id = last_seq_id + 1
        if seq_id != expected_seq_id:
            logger.error(f"Sequence irregularity: expected {expected_seq_id}, got {seq_id}")
            raise DataQualityError(
                f"Sequence gap or out-of-order: expected {expected_seq_id}, got {seq_id}"
            )
