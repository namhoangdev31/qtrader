import polars as pl
from typing import List, Tuple, Any
from datetime import datetime, timedelta

class WalkForwardPipeline:
    """Manages rolling window training and evaluation to prevent lookahead bias."""
    
    def __init__(
        self, 
        train_size: int, 
        test_size: int, 
        embargo: int = 0
    ) -> None:
        self.train_size = train_size
        self.test_size = test_size
        self.embargo = embargo

    def get_splits(self, df: pl.DataFrame) -> List[Tuple[pl.DataFrame, pl.DataFrame]]:
        """Generates (train, test) splits using rolling windows."""
        splits = []
        n = len(df)
        
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
