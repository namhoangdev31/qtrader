from __future__ import annotations

from collections.abc import Callable, Iterator

import polars as pl


class WalkforwardEngine:
    """
    Validation engine for Out-Of-Sample (OOS) performance testing.

    Split Strategy:
    - Train: [t0, t1]
    - Test: [t1, t2] (Forward period)
    """

    @staticmethod
    def generate_windows(
        n_rows: int, train_size: int, test_size: int, step: int = 0
    ) -> Iterator[tuple[slice, slice]]:
        """
        Generate train/test slice pairs for rolling validation.

        Args:
            n_rows: Total number of rows in dataset.
            train_size: Number of rows for training window.
            test_size: Number of rows for testing (OOS) window.
            step: Step size for rolling. If 0, step = test_size (non-overlapping OOS).

        Yields:
            Tuple of (train_slice, test_slice).
        """
        if n_rows < train_size + test_size:
            return

        actual_step = step if step > 0 else test_size

        start = 0
        while start + train_size + test_size <= n_rows:
            train_slice = slice(start, start + train_size)
            test_slice = slice(start + train_size, start + train_size + test_size)
            yield train_slice, test_slice

            start += actual_step

    @staticmethod
    def run_validation(
        df: pl.DataFrame,
        model_pipeline: Callable[[pl.DataFrame, pl.DataFrame], pl.DataFrame],
        train_size: int,
        test_size: int,
        step: int = 0,
    ) -> pl.DataFrame:
        """
        Execute walk-forward validation across the dataset.

        Args:
            df: Full dataset.
            model_pipeline: Callable that takes (train_df, test_df) and
                            returns OOS predictions/metrics DataFrame.
            train_size: Training window size.
            test_size: Testing window size.
            step: Step size for rolling windows.

        Returns:
            Concatenated OOS results.
        """
        results: list[pl.DataFrame] = []

        for train_slice, test_slice in WalkforwardEngine.generate_windows(
            df.height, train_size, test_size, step
        ):
            train_df = df.slice(train_slice.start, train_slice.stop - train_slice.start)
            test_df = df.slice(test_slice.start, test_slice.stop - test_slice.start)

            oos_result = model_pipeline(train_df, test_df)
            results.append(oos_result)

        if not results:
            return pl.DataFrame()

        return pl.concat(results)
