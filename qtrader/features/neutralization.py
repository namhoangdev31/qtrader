
import numpy as np
import polars as pl


class FactorNeutralizer:
    """Neutralizes factors against risk factors or sectors."""
    
    @staticmethod
    def neutralize(
        df: pl.DataFrame, 
        factor_col: str, 
        group_col: str = "sector"
    ) -> pl.Series:
        """
        Z-score normalization within each group (e.g., sector neutralization).
        Ensures factor is market-neutral or sector-neutral.
        """
        if group_col not in df.columns:
            return df[factor_col]
            
        return df.with_columns([
            ((pl.col(factor_col) - pl.col(factor_col).mean().over(group_col)) / 
             (pl.col(factor_col).std().over(group_col) + 1e-8)).alias(f"{factor_col}_neut")
        ]).select(f"{factor_col}_neut").to_series()

    @staticmethod
    def neutralize_by_map(
        df: pl.DataFrame, 
        factor_col: str, 
        symbol_col: str, 
        mapping: Dict[str, str]
    ) -> pl.Series:
        """Neutralizes a factor using an external symbol-to-group mapping."""
        # 1. Map symbols to groups
        df_mapped = df.with_columns([
            pl.col(symbol_col).map_dict(mapping).alias("_group")
        ])
        
        # 2. Neutralize by mapped group
        return FactorNeutralizer.neutralize(df_mapped, factor_col, group_col="_group")

    @staticmethod
    def orthogonalize(df: pl.DataFrame, factor_cols: list[str]) -> pl.DataFrame:
        """
        PCA-based orthogonalization to remove correlation between factors.
        Returns a DataFrame of independent principle components.
        """
        from sklearn.decomposition import PCA
        
        data = df.select(factor_cols).to_numpy()
        # Handle NAs
        data = np.nan_to_num(data)
        
        pca = PCA(n_components=len(factor_cols))
        orthogonal_data = pca.fit_transform(data)
        
        return pl.DataFrame({
            f"factor_pc_{i}": orthogonal_data[:, i] for i in range(len(factor_cols))
        })
