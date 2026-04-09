from __future__ import annotations

from dataclasses import dataclass

import polars as pl

__all__ = ["PurgedKFoldCV", "WalkForwardPipeline"]


@dataclass(slots=True)
class WalkForwardPipeline:
    train_size: int
    test_size: int
    embargo: int = 0

    def get_splits(self, df: pl.DataFrame) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
        splits: list[tuple[pl.DataFrame, pl.DataFrame]] = []
        n = df.height
        start = 0
        while start + self.train_size + self.embargo + self.test_size <= n:
            train_end = start + self.train_size
            test_start = train_end + self.embargo
            test_start + self.test_size
            train_df = df.slice(start, self.train_size)
            test_df = df.slice(test_start, self.test_size)
            splits.append((train_df, test_df))
            start += self.test_size
        return splits


@dataclass(slots=True)
class PurgedKFoldCV:
    n_splits: int = 5
    embargo_pct: float = 0.01

    def split(
        self, df: pl.DataFrame, events_col: str = "timestamp"
    ) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
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
            test_end = (k + 1) * fold_size if k < self.n_splits - 1 else n
            test_mask = (keyed["idx"] >= test_start) & (keyed["idx"] < test_end)
            test_df = keyed.filter(test_mask)
            if test_df.height == 0:
                continue
            test_start_time = test_df.select(events_col).min().item()
            test_end_time = test_df.select(events_col).max().item()
            purge_mask = ~(
                (keyed[events_col] >= test_start_time) & (keyed[events_col] <= test_end_time)
            )
            if embargo > 0:
                embargo_end_idx = min(test_end + embargo, n)
                embargo_mask = ~((keyed["idx"] >= test_end) & (keyed["idx"] < embargo_end_idx))
                train_mask = purge_mask & embargo_mask & ~test_mask
            else:
                train_mask = purge_mask & ~test_mask
            train_df = keyed.filter(train_mask).drop("idx")
            test_df_clean = test_df.drop("idx")
            if train_df.height == 0 or test_df_clean.height == 0:
                continue
            splits.append((train_df, test_df_clean))
        return splits


if __name__ == "__main__":
    _df = pl.DataFrame(
        {"timestamp": pl.arange(0, 100, eager=True), "x": pl.arange(0, 100, eager=True)}
    )
    _wf = WalkForwardPipeline(train_size=50, test_size=10, embargo=5)
    _splits = _wf.get_splits(_df)
    if not _splits:
        raise ValueError("Walk-forward pipeline failed to generate splits")
    _cv = PurgedKFoldCV(n_splits=5, embargo_pct=0.02)
    _cv_splits = _cv.split(_df, events_col="timestamp")
    if not _cv_splits:
        raise ValueError("Purged K-Fold CV failed to generate splits")
