
import numpy as np
import polars as pl
from sklearn.mixture import GaussianMixture


class RegimeDetector:
    """
    Identifies market regimes (e.g., Bull, Bear, Sideways, High Vol)
    using unsupervised learning (Gaussian Mixture Models).
    """
    
    def __init__(self, n_regimes: int = 3) -> None:
        self.n_regimes = n_regimes
        self.model = GaussianMixture(
            n_components=n_regimes, 
            covariance_type="full", 
            random_state=42
        )
        self.is_fitted = False

    def fit(self, df: pl.DataFrame, feature_cols: list[str]) -> None:
        """Trains the GMM model on historical features (e.g., returns, volatility)."""
        data = df.select(feature_cols).to_numpy()
        # Clean NAs
        data = np.nan_to_num(data)
        
        self.model.fit(data)
        self.is_fitted = True

    def predict_regime(self, df: pl.DataFrame, feature_cols: list[str]) -> pl.Series:
        """Predicts the current regime for each row in the DataFrame."""
        if not self.is_fitted:
            raise RuntimeError("RegimeDetector must be fitted before prediction.")
            
        data = df.select(feature_cols).to_numpy()
        data = np.nan_to_num(data)
        
        regimes = self.model.predict(data)
        return pl.Series("market_regime", regimes)

    def get_regime_stats(self, df: pl.DataFrame, regimes: pl.Series) -> pl.DataFrame:
        """Calculates statistics for each identified regime."""
        df_with_regime = df.with_columns(regimes)
        
        # Group by regime and calculate mean returns and volatility
        return df_with_regime.group_by("market_regime").agg([
            pl.col("close").pct_change().mean().alias("avg_return"),
            pl.col("close").pct_change().std().alias("avg_volatility"),
            pl.count().alias("count")
        ]).sort("market_regime")
