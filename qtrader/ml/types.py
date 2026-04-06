"""ML Shared Types — Central Schema for Atomic Trio.

Contains common data structures for decisions, risk classification,
and forecasting used across different model adapters and the main pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionAction(str, Enum):
    """Trading decision actions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    HEDGE = "HEDGE"
    CLOSE_ALL = "CLOSE_ALL"
    REDUCE_POSITION = "REDUCE_POSITION"


@dataclass(slots=True)
class TradingDecision:
    """Output of a decision controller (LLM or Rule-based)."""

    action: DecisionAction
    confidence: float
    reasoning: str
    risk_adjustment: float  # 0.0 (no risk) to 1.0 (max risk)
    position_size_multiplier: float  # 0.0 (no position) to 1.0 (full size)
    stop_loss_pct: float
    take_profit_pct: float
    time_horizon: str  # "short", "medium", "long"
    explanation: str  # ML Explainability for Standash §13
    inference_time_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "risk_adjustment": self.risk_adjustment,
            "position_size_multiplier": self.position_size_multiplier,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "time_horizon": self.time_horizon,
            "explanation": self.explanation,
            "inference_time_ms": round(self.inference_time_ms, 2),
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class RiskClassificationResult:
    """Result of risk classification (TabPFN or LLM)."""

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
