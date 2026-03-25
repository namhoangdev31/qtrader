from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
import shap


class FeatureImportance:
    """
    Analyzer to compute and rank feature importance using SHAP values.
    Provides explainability for alpha models by quantifying feature contributions.
    """

    @staticmethod
    def compute_importance(
        model: Any,
        x_data: pl.DataFrame | np.ndarray[Any, Any],
        feature_names: list[str] | None = None,
    ) -> list[tuple[str, float]]:
        """
        Calculate global feature importance using SHAP values.

        Args:
            model: Trained model (e.g., LightGBM, XGBoost, or sklearn regressor).
            x_data: Feature matrix used for importance calculation.
            feature_names: Optional list of feature names. If None and x_data is a
                          DataFrame, column names will be used.

        Returns:
            Sorted list of (feature_name, importance_score) tuples.
        """
        # Convert to numpy for SHAP if needed
        x_baked = x_data.to_numpy() if isinstance(x_data, pl.DataFrame) else x_data

        # Determine feature names
        if feature_names is None:
            if isinstance(x_data, pl.DataFrame):
                feature_names = x_data.columns
            else:
                feature_names = [f"feature_{i}" for i in range(x_baked.shape[1])]

        # Use SHAP Explainer
        # For tree models, TreeExplainer is much faster
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(x_baked)
        except Exception:
            # Fallback to KernelExplainer for general models
            # Note: KernelExplainer can be very slow on large datasets
            # We take a small sample if needed or just use standard Explainer
            explainer = shap.Explainer(model, x_baked)
            shap_values = explainer(x_baked).values

        # Compute mean absolute SHAP value per feature
        # shap_values can be a list (for multi-class) or an array
        if isinstance(shap_values, list):
            # Take the first class (for binary/regression it's often just the first)
            # but usually for regression it's just an array
            # If it's a list, we average absolute values across all rows
            abs_shap = np.abs(shap_values[0]).mean(axis=0)
        else:
            abs_shap = np.abs(shap_values).mean(axis=0)

        # Create ranking
        importance_dict = dict(zip(feature_names, abs_shap.tolist(), strict=True))
        sorted_importance = sorted(
            importance_dict.items(),
            key=lambda item: item[1],
            reverse=True,
        )

        return sorted_importance

    @staticmethod
    def get_top_features(importance_results: list[tuple[str, float]], top_k: int = 10) -> list[str]:
        """
        Extract the top K feature names from importance results.

        Args:
            importance_results: Output from compute_importance.
            top_k: Number of top features to return.

        Returns:
            List of feature names.
        """
        return [name for name, _ in importance_results[:top_k]]
