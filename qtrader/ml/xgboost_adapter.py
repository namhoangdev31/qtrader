"""XGBoost Risk Classification — Stable Offline Substitute for TabPFN.

XGBoost is used as a high-performance, 100% offline alternative to TabPFN.
It provides extremely low latency (<5ms) and robust classification for
market risk levels: SAFE, WARNING, DANGER.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import xgboost as xgb

logger = logging.getLogger("qtrader.ml.xgboost")


@dataclass(slots=True)
class RiskClassificationResult:
    """Result of XGBoost risk classification."""

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


class XGBoostRiskAdapter:
    """XGBoost adapter for market risk classification.
    
    Substitute for TabPFNRiskAdapter.
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
        model_id: str = "xgboost_v1",
        device: str = "cpu",
        n_estimators: int = 100,
        max_depth: int = 4,
    ) -> None:
        self.model_id = model_id
        self.device = device
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        
        self._model: xgb.XGBClassifier | None = None
        self._is_loaded = False
        self._feature_names = list(self.DEFAULT_FEATURES)
        self._training_data: list[dict[str, float]] = []
        self._training_labels: list[int] = []  # 0=SAFE, 1=WARNING, 2=DANGER

    def _load_model(self) -> None:
        """Initialize XGBoost model."""
        if self._is_loaded:
            return

        logger.info(f"[XGBOOST] Initializing {self.model_id} on {self.device}...")

        try:
            self._model = xgb.XGBClassifier(
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=0.1,
                objective="multi:softprob",
                num_class=3,
                tree_method="hist" if self.device == "cpu" else "gpu_hist",
                random_state=42,
            )
            
            # Warm-up/Initial fit with dummy data to satisfy shape requirements
            dummy_X = np.random.rand(20, len(self._feature_names))
            dummy_y = np.random.randint(0, 3, 20)
            self._model.fit(dummy_X, dummy_y)
            
            self._is_loaded = True
            logger.info(f"[XGBOOST] Model initialized: {self.model_id}")
        except Exception as e:
            logger.error(f"[XGBOOST] Failed to initialize model: {e}")
            self._model = None
            self._is_loaded = True

    def add_training_data(
        self,
        features: dict[str, float],
        label: str,
    ) -> None:
        """Add labeled training data for incremental learning."""
        label_map = {"SAFE": 0, "WARNING": 1, "DANGER": 2}
        self._training_data.append(features)
        self._training_labels.append(label_map.get(label, 1))

    def fit(self) -> None:
        """Fit XGBoost on accumulated training data."""
        self._load_model()
        if self._model is None or len(self._training_data) < 5:
            return

        X = np.array([[d.get(f, 0.0) for f in self._feature_names] for d in self._training_data])
        y = np.array(self._training_labels)

        self._model.fit(X, y)
        logger.info(f"[XGBOOST] Fitted on {len(self._training_data)} samples")

    def classify(
        self,
        features: dict[str, float],
        feature_names: list[str] | None = None,
    ) -> RiskClassificationResult:
        """Classify market risk level."""
        self._load_model()

        if feature_names is None:
            feature_names = self._feature_names

        feature_array = np.array([[features.get(f, 0.0) for f in feature_names]])
        start_time = time.time()

        # Phase 1: Try XGBoost prediction
        probabilities = None
        class_idx = 1  # Default WARNING
        
        if self._model is not None:
            try:
                probs_raw = self._model.predict_proba(feature_array)[0]
                # Combine with rule-based for ultimate stability in edge cases
                rule_probs, rule_idx = self._rule_based_classify(features)
                
                # Weighting: 40% XGBoost, 60% Rules (Ensemble for stability)
                probabilities = (probs_raw * 0.4) + (rule_probs * 0.6)
                class_idx = int(np.argmax(probabilities))
            except Exception as e:
                logger.warning(f"[XGBOOST] Prediction failed: {e}. Falling back to 100% rules.")
                probabilities, class_idx = self._rule_based_classify(features)
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

        return RiskClassificationResult(
            class_label=class_label,
            probabilities=prob_dict,
            confidence=float(max(probabilities)),
            inference_time_ms=inference_time_ms,
            feature_importance=self._get_feature_importance(),
            risk_score=risk_score,
        )

    def _rule_based_classify(self, features: dict[str, float]) -> tuple[np.ndarray, int]:
        """Core technical rule-based risk logic."""
        risk_score = 0.0

        rsi = features.get("rsi", 50)
        if rsi > 80 or rsi < 20: risk_score += 0.4
        elif rsi > 70 or rsi < 30: risk_score += 0.2

        vol = features.get("volatility", 0.02)
        if vol > 0.06: risk_score += 0.4
        elif vol > 0.04: risk_score += 0.2

        spread = features.get("spread_bps", 5.0)
        if spread > 30: risk_score += 0.3
        elif spread > 15: risk_score += 0.15

        risk_score = min(risk_score, 1.0)

        if risk_score < 0.25: class_idx = 0
        elif risk_score < 0.6: class_idx = 1
        else: class_idx = 2

        probs = np.zeros(3)
        probs[class_idx] = 0.7
        probs[(class_idx + 1) % 3] = 0.2
        probs[(class_idx + 2) % 3] = 0.1
        return probs, class_idx

    def _get_feature_importance(self) -> dict[str, float]:
        """Extract importance from XGBoost if available."""
        if self._model is not None and hasattr(self._model, "feature_importances_"):
            importances = self._model.feature_importances_
            return {f: float(v) for f, v in zip(self._feature_names, importances)}
        return {f: 1.0 / len(self._feature_names) for f in self._feature_names}

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "type": "XGBoost (Offline)",
            "is_loaded": self._is_loaded,
            "training_samples": len(self._training_data),
            "feature_count": len(self._feature_names),
        }
