
from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["PurgedKFoldCV", "WalkForwardPipeline"]


@dataclass(slots=True)
class WalkForwardPipeline:
    """Rolling-window walk-forward splitter with optional embargo.

    Args:
        train_size: Number of rows in each training window.
        test_size: Number of rows in each test window.
        embargo: Number of rows to skip between train and test to reduce leakage.
    """

    train_size: int
    test_size: int
    embargo: int = 0

    def get_splits(self, df: pl.DataFrame) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
        """Generate (train, test) splits using rolling windows.

        Args:
            df: Input DataFrame ordered by time.

        Returns:
            List of (train_df, test_df) pairs.
        """
        splits: list[tuple[pl.DataFrame, pl.DataFrame]] = []
        n = df.height

        start = 0
        while start + self.train_size + self.embargo + self.test_size <= n:
            train_end = start + self.train_size
            test_start = train_end + self.embargo
            test_end = test_start + self.test_size

            train_df = df.slice(start, self.train_size)
            test_df = df.slice(test_start, self.test_size)

            splits.append((train_df, test_df))

            # Slide window forward by test_size for non-overlapping tests
            start += self.test_size

        return splits


@dataclass(slots=True)
class PurgedKFoldCV:
    """Combinatorial Purged Cross-Validation for time series.

    Prevents data leakage via purging overlapping samples and applying an
    embargo period after each test fold, following Lopez de Prado's CPCV.

    Args:
        n_splits: Number of CV folds.
        embargo_pct: Fraction of the dataset to embargo after each test period.
    """

    n_splits: int = 5
    embargo_pct: float = 0.01

    def split(
        self,
        df: pl.DataFrame,
        events_col: str = "timestamp",
    ) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
        """Generate purged (train, test) splits.

        Args:
            df: Time-ordered DataFrame.
            events_col: Column representing event time (timestamp or index-like).

        Returns:
            List of (train_df, test_df) folds.
        """
        if events_col not in df.columns:
            raise ValueError(f"Column '{events_col}' not found in DataFrame.")
        if self.n_splits <= 1:
            raise ValueError("n_splits must be greater than 1.")

        n = df.height
        indices = pl.Series("idx", list(range(n)))
        keyed = df.with_columns(indices)

        fold_size = n // self.n_splits
        embargo = int(self.embargo_pct * n)

        splits: list[tuple[pl.DataFrame, pl.DataFrame]] = []

        for k in range(self.n_splits):
            test_start = k * fold_size
            # Last fold may be larger due to integer division remainder.
            test_end = (k + 1) * fold_size if k < self.n_splits - 1 else n

            test_mask = (keyed["idx"] >= test_start) & (keyed["idx"] < test_end)
            test_df = keyed.filter(test_mask)

            if test_df.height == 0:
                continue

            test_start_time = test_df.select(events_col).min().item()
            test_end_time = test_df.select(events_col).max().item()

            # Purging: remove any train samples overlapping the test period.
            purge_mask = ~(
                (keyed[events_col] >= test_start_time)
                & (keyed[events_col] <= test_end_time)
            )

            # Embargo: remove samples within embargo window after test_end_time.
            if embargo > 0:
                embargo_end_idx = min(test_end + embargo, n)
                embargo_mask = ~(
                    (keyed["idx"] >= test_end) & (keyed["idx"] < embargo_end_idx)
                )
                train_mask = purge_mask & embargo_mask & (~test_mask)
            else:
                train_mask = purge_mask & (~test_mask)

            train_df = keyed.filter(train_mask).drop("idx")
            test_df_clean = test_df.drop("idx")

            if train_df.height == 0 or test_df_clean.height == 0:
                continue
            splits.append((train_df, test_df_clean))

        return splits


if __name__ == "__main__":
    _df = pl.DataFrame(
        {
            "timestamp": pl.arange(0, 100, eager=True),
            "x": pl.arange(0, 100, eager=True),
        }
    )
    _wf = WalkForwardPipeline(train_size=50, test_size=10, embargo=5)
    _splits = _wf.get_splits(_df)
    assert len(_splits) > 0

    _cv = PurgedKFoldCV(n_splits=5, embargo_pct=0.02)
    _cv_splits = _cv.split(_df, events_col="timestamp")
    assert len(_cv_splits) > 0

