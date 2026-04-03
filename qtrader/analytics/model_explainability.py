"""Model Explainability — Standash §13.

Factor attribution for ML model decisions using SHAP-style analysis.
Provides institutional transparency: every trade decision must be explainable
by attributing the signal to specific features/factors.

This module implements a lightweight SHAP approximation that doesn't require
the external shap library, using permutation-based feature importance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import polars as pl

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FeatureAttribution:
    """Attribution of a single prediction to its features."""

    feature_name: str
    shap_value: float
    absolute_value: float
    direction: str  # POSITIVE, NEGATIVE, NEUTRAL
    feature_value: float


@dataclass(slots=True)
class ModelExplanation:
    """Complete explanation of a model's prediction."""

    prediction: float
    base_value: float
    attributions: list[FeatureAttribution]
    top_features: list[str]
    confidence: float
    timestamp: float = 0.0


class ModelExplainer:
    """Model Explainability Engine — Standash §13.

    Provides SHAP-style feature attribution for model predictions using
    permutation-based importance analysis.

    For each prediction, explains:
    - Which features contributed most to the decision
    - Direction of each feature's contribution (positive/negative)
    - Magnitude of each feature's contribution (SHAP value)
    - Overall confidence in the explanation
    """

    def __init__(
        self,
        feature_names: list[str] | None = None,
        n_permutations: int = 50,
        random_seed: int = 42,
    ) -> None:
        self.feature_names = feature_names or []
        self.n_permutations = n_permutations
        self.random_seed = random_seed
        self._base_value: float = 0.0
        self._feature_importances: dict[str, float] = {}
        self._explanation_history: list[ModelExplanation] = []
        self._max_history = 10_000

    def fit(
        self,
        model_fn,
        X: pl.DataFrame,
        y: pl.Series | None = None,
    ) -> dict[str, float]:
        """Compute global feature importances using permutation importance.

        Args:
            model_fn: Callable that takes a DataFrame and returns predictions.
            X: Feature DataFrame.
            y: Optional target series for scoring.

        Returns:
            Dictionary of feature_name -> importance score.
        """
        if X.is_empty() or not self.feature_names:
            return {}

        import numpy as np

        rng = np.random.default_rng(self.random_seed)

        # Baseline prediction
        baseline_pred = model_fn(X)
        if isinstance(baseline_pred, pl.DataFrame):
            baseline_score = float(baseline_pred.select(pl.all().mean()).to_series().mean())
        elif isinstance(baseline_pred, pl.Series):
            baseline_score = float(baseline_pred.mean())
        else:
            baseline_score = float(np.mean(baseline_pred))

        self._base_value = baseline_score
        importances: dict[str, float] = {}

        for feature in self.feature_names:
            if feature not in X.columns:
                continue

            # Permute feature and measure prediction degradation
            score_diffs = []
            for _ in range(min(self.n_permutations, 20)):
                X_permuted = X.with_columns([pl.col(feature).shuffle()])
                permuted_pred = model_fn(X_permuted)
                if isinstance(permuted_pred, pl.DataFrame):
                    perm_score = float(permuted_pred.select(pl.all().mean()).to_series().mean())
                elif isinstance(permuted_pred, pl.Series):
                    perm_score = float(permuted_pred.mean())
                else:
                    perm_score = float(np.mean(permuted_pred))
                score_diffs.append(abs(baseline_score - perm_score))

            importances[feature] = float(np.mean(score_diffs))

        self._feature_importances = importances
        return importances

    def explain_prediction(
        self,
        model_fn,
        X: pl.DataFrame,
        row_idx: int = 0,
    ) -> ModelExplanation:
        """Explain a single prediction using local feature attribution.

        Args:
            model_fn: Callable that takes a DataFrame and returns predictions.
            X: Feature DataFrame (single row or multi-row).
            row_idx: Index of the row to explain.

        Returns:
            ModelExplanation with feature attributions.
        """
        import time
        import numpy as np

        if X.is_empty() or row_idx >= X.height:
            return ModelExplanation(
                prediction=0.0,
                base_value=self._base_value,
                attributions=[],
                top_features=[],
                confidence=0.0,
                timestamp=time.time(),
            )

        # Get the row to explain
        row = X.slice(row_idx, 1)
        prediction = model_fn(row)
        if isinstance(prediction, pl.DataFrame):
            pred_value = float(prediction.select(pl.all().mean()).to_series().mean())
        elif isinstance(prediction, pl.Series):
            pred_value = float(prediction.mean())
        else:
            pred_value = float(np.asarray(prediction).flatten()[0])

        # Compute local attributions using leave-one-out
        attributions: list[FeatureAttribution] = []
        for feature in self.feature_names:
            if feature not in X.columns:
                continue

            feature_val = float(row[feature].item())

            # Leave-one-out: replace feature with mean
            col_mean = X[feature].mean() or 0.0
            X_loo = X.with_columns(
                [
                    pl.when(pl.arange(0, X.height) == row_idx)
                    .then(pl.lit(col_mean))
                    .otherwise(pl.col(feature))
                    .alias(feature)
                ]
            )

            loo_pred = model_fn(X_loo)
            if isinstance(loo_pred, pl.DataFrame):
                loo_value = float(loo_pred.select(pl.all().mean()).to_series().mean())
            elif isinstance(loo_pred, pl.Series):
                loo_value = float(loo_pred.mean())
            else:
                loo_value = float(np.asarray(loo_pred).flatten()[0])

            shap_value = pred_value - loo_value
            abs_value = abs(shap_value)

            if abs_value > 0.01:
                direction = "POSITIVE" if shap_value > 0 else "NEGATIVE"
            else:
                direction = "NEUTRAL"

            attributions.append(
                FeatureAttribution(
                    feature_name=feature,
                    shap_value=shap_value,
                    absolute_value=abs_value,
                    direction=direction,
                    feature_value=feature_val,
                )
            )

        # Sort by absolute contribution
        attributions.sort(key=lambda a: a.absolute_value, reverse=True)
        top_features = [a.feature_name for a in attributions[:5]]

        # Compute confidence based on attribution coverage
        total_attribution = sum(a.absolute_value for a in attributions)
        unexplained = abs(pred_value - self._base_value)
        confidence = min(1.0, total_attribution / (unexplained + 1e-8)) if unexplained > 0 else 1.0

        explanation = ModelExplanation(
            prediction=pred_value,
            base_value=self._base_value,
            attributions=attributions,
            top_features=top_features,
            confidence=confidence,
            timestamp=time.time(),
        )

        # Track history
        self._explanation_history.append(explanation)
        if len(self._explanation_history) > self._max_history:
            self._explanation_history = self._explanation_history[-self._max_history // 2 :]

        return explanation

    def get_global_importance_ranking(self) -> list[tuple[str, float]]:
        """Return features ranked by global importance."""
        return sorted(
            self._feature_importances.items(),
            key=lambda x: x[1],
            reverse=True,
        )

    def get_explanation_summary(self) -> dict[str, Any]:
        """Return summary statistics of explanations."""
        if not self._explanation_history:
            return {"count": 0}

        confidences = [e.confidence for e in self._explanation_history]
        feature_counts: dict[str, int] = {}
        for exp in self._explanation_history:
            for feat in exp.top_features:
                feature_counts[feat] = feature_counts.get(feat, 0) + 1

        return {
            "count": len(self._explanation_history),
            "avg_confidence": sum(confidences) / len(confidences),
            "min_confidence": min(confidences),
            "max_confidence": max(confidences),
            "top_features_overall": sorted(
                feature_counts.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "global_importance": self.get_global_importance_ranking(),
        }
