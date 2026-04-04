"""Phi-2 Decision Controller — Microsoft HF Model.

Phi-2 đóng vai trò "Người điều phối" trong bộ ba nguyên tử:
- Đọc output của Chronos-2 (dự báo giá) và TabPFN (phân loại rủi ro)
- Kết hợp với quy tắc hệ thống (Standash compliance)
- Ra quyết định cuối cùng: BUY, SELL, HOLD, hay HEDGE

HF Model: https://huggingface.co/microsoft/phi-2
Phi-2 (2.7B params) rất nhẹ trên Mac M4 (~2.5-5GB RAM).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("qtrader.ml.phi2_controller")


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
    """Output of the Phi-2 decision controller."""

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


class Phi2DecisionController:
    """Phi-2 Decision Controller.

    Orchestrates the Atomic Trio pipeline:
    1. Receives forecast from Chronos-2
    2. Receives risk classification from TabPFN
    3. Applies decision logic (rule-based or Phi-2 LLM)
    4. Returns TradingDecision with full explainability

    For Mac M4, uses MLX for Phi-2 inference when available.
    Falls back to rule-based decision engine when Phi-2 is not loaded.
    """

    def __init__(
        self,
        model_id: str = "mlx-community/phi-2",
        model_size: str = "2.7b",
        backend: str = "auto",
        use_rule_based_fallback: bool = True,
        hf_token: str | None = None,
    ) -> None:
        self.model_id = model_id
        self.model_size = model_size
        self.backend = backend
        self.use_rule_based_fallback = use_rule_based_fallback
        self.hf_token = hf_token or os.environ.get("HUGGINGFACE_TOKEN")
        self._model: Any = None
        self._tokenizer: Any = None
        self._is_loaded = False
        self._decision_count: int = 0

    def _load_model(self) -> None:
        """Load Phi-2 model."""
        if self._is_loaded:
            return

        if self.backend == "auto":
            try:
                import mlx.core as mx  # noqa: F401

                self.backend = "mlx"
                logger.info("[PHI2] Using MLX backend (Mac M4 optimized)")
            except ImportError:
                self.backend = "transformers"
                logger.info("[PHI2] MLX not available, using transformers backend")

        if self.backend == "mlx":
            self._load_mlx_model()
        else:
            self._load_transformers_model()

        self._is_loaded = True
        logger.info(f"[PHI2] Model loaded: {self.model_size} ({self.backend})")

    def _load_mlx_model(self) -> None:
        """Load Phi-2 using MLX for Mac M4."""
        try:
            from mlx_lm import load  # type: ignore

            self._model, self._tokenizer = load(self.model_id)
        except ImportError:
            logger.warning("[PHI2] mlx_lm not installed, using rule-based fallback")
            self._model = None

    def _load_transformers_model(self) -> None:
        """Load Phi-2 using transformers."""
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            self._tokenizer = AutoTokenizer.from_pretrained("microsoft/phi-2")
            self._model = AutoModelForCausalLM.from_pretrained(
                "microsoft/phi-2",
                device_map="auto",
                torch_dtype="auto",
            )
        except ImportError:
            logger.warning("[PHI2] transformers not installed, using rule-based fallback")
            self._model = None

    def decide(
        self,
        chronos_forecast: dict[str, Any] | None = None,
        tabpfn_risk: dict[str, Any] | None = None,
        market_context: dict[str, Any] | None = None,
        system_state: dict[str, Any] | None = None,
    ) -> TradingDecision:
        """Make a trading decision based on model outputs and context.

        Args:
            chronos_forecast: Output from ChronosForecastAdapter.predict().to_dict()
            tabpfn_risk: Output from TabPFNRiskAdapter.classify().to_dict()
            market_context: Current market conditions (price, volume, spread, etc.)
            system_state: Current system state (positions, PnL, kill switch status)

        Returns:
            TradingDecision with action, confidence, reasoning, and explainability.
        """
        start_time = time.time()
        self._decision_count += 1

        # Try LLM-based decision first
        if self._model is not None:
            try:
                decision = self._llm_decide(
                    chronos_forecast, tabpfn_risk, market_context, system_state
                )
                decision.inference_time_ms = (time.time() - start_time) * 1000
                return decision
            except Exception as e:
                logger.warning(f"[PHI2] LLM decision failed: {e}, using rule-based fallback")

        # Fallback to rule-based decision engine
        decision = self._rule_based_decide(
            chronos_forecast, tabpfn_risk, market_context, system_state
        )
        decision.inference_time_ms = (time.time() - start_time) * 1000
        return decision

    def _llm_decide(
        self,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
        market_context: dict[str, Any] | None,
        system_state: dict[str, Any] | None,
    ) -> TradingDecision:
        """Make decision using Phi-2 LLM."""
        # Build prompt
        prompt = self._build_prompt(chronos_forecast, tabpfn_risk, market_context, system_state)

        if self.backend == "mlx":
            response = self._generate_mlx(prompt)
        else:
            response = self._generate_transformers(prompt)

        # Parse response into TradingDecision
        return self._parse_llm_response(response, chronos_forecast, tabpfn_risk)

    def _build_prompt(
        self,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
        market_context: dict[str, Any] | None,
        system_state: dict[str, Any] | None,
    ) -> str:
        instruct = (
            "Instruct: Act as a quantitative trading decision engine. "
            "Analyze inputs and provide a trading decision in strict JSON format.\n"
            "Required Fields: action (BUY/SELL/HOLD/HEDGE/CLOSE_ALL/REDUCE_POSITION), "
            "confidence (0-1), reasoning, risk_adjustment (0-1), position_size_multiplier (0-1), "
            "stop_loss_pct, take_profit_pct, time_horizon (short/medium/long), explanation.\n\n"
        )
        prompt = instruct

        if chronos_forecast:
            trend = chronos_forecast.get("trend_direction", "UNKNOWN")
            prompt += f"Chronos-2 Forecast:\n- Trend: {trend}\n"
            mean_vals = chronos_forecast.get("mean")
            if mean_vals:
                # Chronos-2 mean might be a list or array
                mean_val = mean_vals[-1]
                prompt += f"- Target Price Change: {float(mean_val):.2%}\n"

        if tabpfn_risk:
            label = tabpfn_risk.get("class_label", "UNKNOWN")
            prompt += f"TabPFN Risk Analysis:\n- Label: {label}\n"
            prompt += f"- Probabilities: {tabpfn_risk.get('probabilities', {})}\n"

        if market_context:
            prompt += f"Market Context:\n{json.dumps(market_context, indent=2)}\n"

        if system_state:
            prompt += f"System State:\n{json.dumps(system_state, indent=2)}\n"

        prompt += "\nOutput: {"
        return prompt

    def _generate_mlx(self, prompt: str) -> str:
        """Generate response using MLX."""
        from mlx_lm import generate  # type: ignore

        return generate(
            self._model,
            self._tokenizer,
            prompt=prompt,
            max_tokens=256,
            temp=0.3,
        )

    def _generate_transformers(self, prompt: str) -> str:
        """Generate response using transformers."""
        inputs = self._tokenizer(prompt, return_tensors="pt")
        outputs = self._model.generate(
            inputs.input_ids,
            max_new_tokens=256,
            temperature=0.3,
            do_sample=True,
        )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)

    def _parse_llm_response(
        self,
        response: str,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
    ) -> TradingDecision:
        """Parse LLM response into TradingDecision."""
        # Extract JSON from response
        try:
            # Find JSON block
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(response[start:end])
            else:
                data = {}
        except (json.JSONDecodeError, ValueError):
            data = {}

        # Default values
        action_str = data.get("action", "HOLD")
        try:
            action = DecisionAction(action_str)
        except ValueError:
            action = DecisionAction.HOLD

        return TradingDecision(
            action=action,
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", "Rule-based fallback decision"),
            risk_adjustment=float(data.get("risk_adjustment", 0.5)),
            position_size_multiplier=float(data.get("position_size_multiplier", 0.5)),
            stop_loss_pct=float(data.get("stop_loss_pct", 2.0)),
            take_profit_pct=float(data.get("take_profit_pct", 5.0)),
            time_horizon=data.get("time_horizon", "short"),
            explanation=data.get("explanation", "Decision based on combined model analysis"),
            inference_time_ms=0.0,  # Set by caller
            metadata={
                "chronos_forecast": chronos_forecast,
                "tabpfn_risk": tabpfn_risk,
                "model_backend": self.backend,
            },
        )

    def _rule_based_decide(
        self,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
        market_context: dict[str, Any] | None,
        system_state: dict[str, Any] | None,
    ) -> TradingDecision:
        """Rule-based decision engine (fallback when Phi-2 is not loaded)."""
        # 0. KILL SWITCH: Highest priority — immediate override
        if system_state and system_state.get("kill_switch_active"):
            return TradingDecision(
                action=DecisionAction.CLOSE_ALL,
                confidence=1.0,
                reasoning="Kill switch active — all positions must be closed immediately",
                risk_adjustment=1.0,
                position_size_multiplier=0.0,
                stop_loss_pct=0.0,
                take_profit_pct=0.0,
                time_horizon="short",
                explanation=(
                    "DECISION: CLOSE_ALL. Kill switch is active. "
                    "All positions must be liquidated immediately per risk protocol. "
                    "No new positions allowed until kill switch is deactivated."
                ),
                inference_time_ms=0.0,
                metadata={
                    "chronos_forecast": chronos_forecast,
                    "tabpfn_risk": tabpfn_risk,
                    "market_context": market_context,
                    "system_state": system_state,
                    "model_backend": "rule_based",
                },
            )

        # Default decision
        action = DecisionAction.HOLD
        confidence = 0.5
        reasoning_parts: list[str] = []
        position_size = 0.5
        stop_loss = 2.0
        take_profit = 5.0
        time_horizon = "short"

        # 1. Chronos-2 forecast analysis
        if chronos_forecast:
            trend = chronos_forecast.get("trend_direction", "FLAT")
            if trend == "BULLISH":
                action = DecisionAction.BUY
                confidence = 0.6
                reasoning_parts.append(f"Chronos predicts {trend} trend")
                position_size = 0.6
            elif trend == "BEARISH":
                action = DecisionAction.SELL
                confidence = 0.6
                reasoning_parts.append(f"Chronos predicts {trend} trend")
                position_size = 0.6
            else:
                reasoning_parts.append("Chronos predicts FLAT trend")

        # 2. TabPFN risk analysis
        if tabpfn_risk:
            risk_class = tabpfn_risk.get("class_label", "SAFE")

            if risk_class == "DANGER":
                action = DecisionAction.HOLD
                confidence = 0.9
                reasoning_parts.append(f"TabPFN classifies risk as {risk_class}")
                position_size = 0.0
                stop_loss = 1.0
            elif risk_class == "WARNING":
                if action == DecisionAction.BUY:
                    action = DecisionAction.HEDGE
                elif action == DecisionAction.SELL:
                    action = DecisionAction.REDUCE_POSITION
                confidence = min(confidence, 0.7)
                reasoning_parts.append(f"TabPFN warns: {risk_class}")
                position_size *= 0.5
                stop_loss = 1.5
            else:
                reasoning_parts.append(f"TabPFN classifies risk as {risk_class}")

        # 3. Market context adjustments
        if market_context:
            spread_bps = market_context.get("spread_bps", 5)
            if spread_bps > 20:
                action = DecisionAction.HOLD
                reasoning_parts.append(f"Wide spread ({spread_bps}bps)")
                position_size = 0.0

            volume_ratio = market_context.get("volume_ratio", 1.0)
            if volume_ratio > 5.0:
                reasoning_parts.append(f"Abnormal volume ({volume_ratio}x)")
                if action == DecisionAction.HOLD:
                    action = DecisionAction.HEDGE

        # 4. System state adjustments
        if system_state:
            current_drawdown = system_state.get("current_drawdown", 0.0)
            if current_drawdown > 0.15:
                action = DecisionAction.REDUCE_POSITION
                reasoning_parts.append(f"High drawdown ({current_drawdown:.1%})")
                position_size *= 0.3

        # Build reasoning
        if not reasoning_parts:
            reasoning_parts.append("No strong signals detected")

        reasoning = "; ".join(reasoning_parts)
        explanation = (
            f"Decision: {action.value}. "
            f"Confidence: {confidence:.0%}. "
            f"Position size: {position_size:.0%}. "
            f"Reasoning: {reasoning}. "
            f"Based on Chronos-2 forecast, TabPFN risk classification, "
            f"market conditions, and system state."
        )

        return TradingDecision(
            action=action,
            confidence=confidence,
            reasoning=reasoning,
            risk_adjustment=1.0 - position_size,
            position_size_multiplier=position_size,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit,
            time_horizon=time_horizon,
            explanation=explanation,
            inference_time_ms=0.0,
            metadata={
                "chronos_forecast": chronos_forecast,
                "tabpfn_risk": tabpfn_risk,
                "market_context": market_context,
                "system_state": system_state,
                "model_backend": "rule_based",
            },
        )

    def get_model_info(self) -> dict[str, Any]:
        """Get model information."""
        return {
            "model_type": "Phi-2",
            "model_size": self.model_size,
            "backend": self.backend,
            "is_loaded": self._is_loaded,
            "estimated_memory_mb": 2700,
            "decision_count": self._decision_count,
        }
