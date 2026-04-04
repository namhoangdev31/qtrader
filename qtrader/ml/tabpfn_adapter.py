"""TabPFN 2.5 Risk Classification — Prior-Labs HF Model.

Uses the official Prior-Labs/tabpfn_2_5 model from HuggingFace:
  pip install tabpfn

TabPFN-2.5 is a transformer-based foundation model that uses in-context
learning to solve tabular prediction problems in a forward pass.
Supports ≤50,000 samples and ≤2,000 features.

Mac M4: Runs efficiently on CPU cores without GPU.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger("qtrader.ml.tabpfn")


@dataclass(slots=True)
class RiskClassificationResult:
    """Result of TabPFN risk classification."""

    class_label: str  # "SAFE", "WARNING", "DANGER"
    probabilities: dict[str, float]
    confidence: float
    inference_time_ms: float
    feature_importance: dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0

    @property
    def is_safe(self) -> bool:
        return self.class_label == "SAFE"

    @property
    def is_warning(self) -> bool:
        return self.class_label == "WARNING"

    @property
    def is_danger(self) -> bool:
        return self.class_label == "DANGER"

    def to_dict(self) -> dict[str, Any]:
        return {
            "class_label": self.class_label,
            "probabilities": self.probabilities,
            "confidence": self.confidence,
            "risk_score": self.risk_score,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "feature_importance": self.feature_importance,
        }


class TabPFNRiskAdapter:
    """TabPFN 2.5 adapter using official Prior-Labs/tabpfn_2_5 from HuggingFace.

    Install: pip install tabpfn
    HF Model: https://huggingface.co/Prior-Labs/tabpfn_2_5
    """

    DEFAULT_FEATURES = [
        "rsi",
        "volatility",
        "volume_ratio",
        "order_imbalance",
        "spread_bps",
        "momentum_1h",
        "momentum_4h",
        "macd_signal",
        "bollinger_width",
        "funding_rate",
    ]

    def __init__(
        self,
        model_id: str = "Prior-Labs/tabpfn_2_5",
        device: str = "cpu",
        n_estimators: int = 4,
        hf_token: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.n_estimators = n_estimators
        self.hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN")
        self._model: Any = None
        self._is_loaded = False
        self._feature_names = list(self.DEFAULT_FEATURES)
        self._training_data: list[dict[str, float]] = []
        self._training_labels: list[int] = []  # 0=SAFE, 1=WARNING, 2=DANGER

    def _load_model(self) -> None:
        if self._is_loaded:
            return

        logger.info(f"[TABPFN] Loading {self.model_id} from HuggingFace...")

        try:
            from tabpfn import TabPFNClassifier  # type: ignore

            self._model = TabPFNClassifier(
                device=self.device,
                n_estimators=self.n_estimators,
            )
            self._is_loaded = True
            logger.info(f"[TABPFN] Model loaded: {self.model_id}")
        except ImportError:
            logger.warning(
                "[TABPFN] tabpfn package not installed. Install with: pip install tabpfn"
            )
            self._model = None
            self._is_loaded = True

    def add_training_data(
        self,
        features: dict[str, float],
        label: str,
    ) -> None:
        """Add labeled training data for fine-tuning TabPFN.

        Args:
            features: Feature dict (rsi, volatility, etc.)
            label: "SAFE", "WARNING", or "DANGER"
        """
        label_map = {"SAFE": 0, "WARNING": 1, "DANGER": 2}
        self._training_data.append(features)
        self._training_labels.append(label_map.get(label, 1))

    def fit(self) -> None:
        """Fit TabPFN on accumulated training data."""
        self._load_model()
        if self._model is None or len(self._training_data) < 10:
            return

        X = np.array([[d.get(f, 0.0) for f in self._feature_names] for d in self._training_data])
        y = np.array(self._training_labels)

        self._model.fit(X, y)
        logger.info(f"[TABPFN] Fitted on {len(self._training_data)} samples")

    def classify(
        self,
        features: dict[str, float],
        feature_names: list[str] | None = None,
    ) -> RiskClassificationResult:
        """Classify market risk level from feature values."""
        self._load_model()

        if feature_names is None:
            feature_names = self._feature_names

        feature_array = np.array([[features.get(f, 0.0) for f in feature_names]])
        start_time = time.time()

        if self._model is not None and hasattr(self._model, "predict_proba"):
            probabilities = self._model.predict_proba(feature_array)[0]
            class_idx = int(np.argmax(probabilities))
        else:
            probabilities, class_idx = self._rule_based_classify(features)

        inference_time_ms = (time.time() - start_time) * 1000

        class_labels = ["SAFE", "WARNING", "DANGER"]
        class_label = class_labels[class_idx]
        prob_dict = {label: float(prob) for label, prob in zip(class_labels, probabilities)}

        risk_score = (
            prob_dict.get("SAFE", 0) * 0.0
            + prob_dict.get("WARNING", 0) * 0.5
            + prob_dict.get("DANGER", 0) * 1.0
        )

        feature_importance = self._estimate_feature_importance(features, feature_names)

        return RiskClassificationResult(
            class_label=class_label,
            probabilities=prob_dict,
            confidence=float(max(probabilities)),
            inference_time_ms=inference_time_ms,
            feature_importance=feature_importance,
            risk_score=risk_score,
        )

    def _rule_based_classify(self, features: dict[str, float]) -> tuple[np.ndarray, int]:
        """Fallback rule-based risk classification."""
        risk_score = 0.0

        rsi = features.get("rsi", 50)
        if rsi > 70 or rsi < 30:
            risk_score += 0.3
        elif rsi > 60 or rsi < 40:
            risk_score += 0.1

        vol = features.get("volatility", 0.02)
        if vol > 0.05:
            risk_score += 0.3
        elif vol > 0.03:
            risk_score += 0.15

        vol_ratio = features.get("volume_ratio", 1.0)
        if vol_ratio > 3.0:
            risk_score += 0.2
        elif vol_ratio > 2.0:
            risk_score += 0.1

        spread = features.get("spread_bps", 5.0)
        if spread > 20:
            risk_score += 0.2
        elif spread > 10:
            risk_score += 0.1

        imbalance = abs(features.get("order_imbalance", 0.0))
        if imbalance > 0.7:
            risk_score += 0.2
        elif imbalance > 0.5:
            risk_score += 0.1

        risk_score = min(risk_score, 1.0)

        if risk_score < 0.3:
            class_idx = 0
        elif risk_score < 0.6:
            class_idx = 1
        else:
            class_idx = 2

        if class_idx == 0:
            probs = np.array([0.8, 0.15, 0.05])
        elif class_idx == 1:
            probs = np.array([0.2, 0.6, 0.2])
        else:
            probs = np.array([0.05, 0.15, 0.8])

        return probs, class_idx

    def _estimate_feature_importance(
        self, features: dict[str, float], feature_names: list[str]
    ) -> dict[str, float]:
        """Estimate feature importance via perturbation."""
        if self._model is None or not hasattr(self._model, "predict_proba"):
            importance = {}
            for name in feature_names:
                val = features.get(name, 0.0)
                importance[name] = abs(val) / max(abs(val) + 1.0, 1.0)
            return importance

        baseline_array = np.array([[features.get(f, 0.0) for f in feature_names]])
        baseline_prob = self._model.predict_proba(baseline_array)[0]
        baseline_class = np.argmax(baseline_prob)

        importance = {}
        for i, name in enumerate(feature_names):
            perturbed = baseline_array.copy()
            perturbed[0, i] = perturbed[0, i] * 1.5 + 0.1
            perturbed_prob = self._model.predict_proba(perturbed)[0]
            importance[name] = float(
                abs(baseline_prob[baseline_class] - perturbed_prob[baseline_class])
            )

        total = sum(importance.values())
        if total > 0:
            importance = {k: v / total for k, v in importance.items()}
        return importance

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "device": self.device,
            "n_estimators": self.n_estimators,
            "is_loaded": self._is_loaded,
            "pipeline_available": self._model is not None,
            "training_samples": len(self._training_data),
            "estimated_memory_mb": 1500,
            "feature_count": len(self._feature_names),
            "class_labels": ["SAFE", "WARNING", "DANGER"],
        }
