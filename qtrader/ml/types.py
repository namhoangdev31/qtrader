from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DecisionAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    HEDGE = "HEDGE"
    CLOSE_ALL = "CLOSE_ALL"
    REDUCE_POSITION = "REDUCE_POSITION"


@dataclass(slots=True)
class TradingDecision:
    action: DecisionAction
    confidence: float
    reasoning: str
    risk_adjustment: float
    position_size_multiplier: float
    stop_loss_pct: float
    take_profit_pct: float
    time_horizon: str
    explanation: str
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
    class_label: str
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
