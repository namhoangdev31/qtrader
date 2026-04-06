"""Ollama Decision Adapter — Mac-Optimized LLM Controller.

Connects to a containerized Ollama instance to perform LLM-based reasoning
for trading decisions. Supports lightweight models like phi3:mini or qwen2:1.5b.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import aiohttp

from qtrader.ml.types import DecisionAction, TradingDecision

logger = logging.getLogger("qtrader.ml.ollama")

HTTP_OK = 200
TIMEOUT_CONNECT = 5
MAX_RAW_RESPONSE_LEN = 1000


class OllamaDecisionAdapter:
    """Ollama Decision Adapter.

    Acts as a Drop-in replacement for Phi2DecisionController.
    Communicates with Ollama API (typically http://ollama:11434).
    """

    def __init__(
        self,
        model_id: str = "phi3:mini",
        base_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.timeout_seconds = timeout_seconds
        self._is_loaded = False
        self._decision_count: int = 0

    async def _check_ready(self) -> bool:
        """Check if Ollama is ready and has the model."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=TIMEOUT_CONNECT,
                ) as resp:
                    if resp.status == HTTP_OK:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        if any(self.model_id in m for m in models):
                            self._is_loaded = True
                            return True
        except Exception as e:
            logger.warning(f"[OLLAMA] Not ready at {self.base_url}: {e}")
        return False

    async def decide(
        self,
        chronos_forecast: dict[str, Any] | None = None,
        tabpfn_risk: dict[str, Any] | None = None,
        market_context: dict[str, Any] | None = None,
        system_state: dict[str, Any] | None = None,
    ) -> TradingDecision:
        """Make a decision using Ollama LLM."""
        start_time = time.time()
        self._decision_count += 1

        prompt = self._build_prompt(chronos_forecast, tabpfn_risk, market_context, system_state)

        try:
            response_text = await self._generate(prompt)
            decision = self._parse_response(response_text, chronos_forecast, tabpfn_risk)
        except Exception as e:
            logger.error(f"[OLLAMA] Inference failed: {e}")
            # Fallback will be handled by AtomicTrio if this raises,
            # but we return a safe HOLD here.
            decision = TradingDecision(
                action=DecisionAction.HOLD,
                confidence=0.0,
                reasoning=f"Ollama error: {e}",
                risk_adjustment=1.0,
                position_size_multiplier=0.0,
                stop_loss_pct=2.0,
                take_profit_pct=5.0,
                time_horizon="short",
                explanation="Decision defaulted to HOLD due to Ollama API error",
                inference_time_ms=0.0,
            )

        decision.inference_time_ms = (time.time() - start_time) * 1000
        return decision

    async def _generate(self, prompt: str) -> str:
        """Call Ollama Generate API."""
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 256,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate", json=payload, timeout=self.timeout_seconds
            ) as resp:
                if resp.status != HTTP_OK:
                    text = await resp.text()
                    raise RuntimeError(f"Ollama returned {resp.status}: {text}")

                data = await resp.json()
                return str(data.get("response", ""))

    def _build_prompt(
        self,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
        market_context: dict[str, Any] | None,
        system_state: dict[str, Any] | None,
    ) -> str:
        """Construct a structured prompt for Ollama."""
        # Use the same format as Phi2 for consistency
        instruct = (
            "System: Act as an institutional quantitative trading engine. "
            "Analyze inputs and provide a trading decision in strict JSON format.\n"
            "JSON Template: {"
            '"action": "BUY/SELL/HOLD/HEDGE", "confidence": float, '
            '"reasoning": string, "risk_adjustment": float, '
            '"position_size_multiplier": float, "stop_loss_pct": float, '
            '"take_profit_pct": float, "time_horizon": "short/medium/long", '
            '"explanation": string'
            "}\n\n"
        )

        data_block = {
            "chronos_2_forecast": chronos_forecast,
            "tabpfn_risk_analysis": tabpfn_risk,
            "market_context": market_context,
            "system_state": system_state,
        }

        return f"{instruct}Input Data:\n{json.dumps(data_block, indent=2)}\n\nOutput JSON:"

    def _parse_response(
        self,
        response: str,
        chronos_forecast: dict[str, Any] | None,
        tabpfn_risk: dict[str, Any] | None,
    ) -> TradingDecision:
        """Parse the raw LLM string into a TradingDecision object."""
        try:
            # Simple extractor for markdown blocks if LLM adds them
            clean_json = response.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[-1].split("```")[0].strip()
            elif "```" in clean_json:
                clean_json = clean_json.split("```")[-1].split("```")[0].strip()

            data = json.loads(clean_json)
        except Exception:
            logger.warning(f"[OLLAMA] Failed to parse JSON from: {response[:100]}...")
            data = {}

        action_str = data.get("action", "HOLD").upper()
        try:
            action = DecisionAction(action_str)
        except ValueError:
            action = DecisionAction.HOLD

        return TradingDecision(
            action=action,
            confidence=float(data.get("confidence", 0.5)),
            reasoning=data.get("reasoning", "Autonomous decision via Ollama"),
            risk_adjustment=float(data.get("risk_adjustment", 0.5)),
            position_size_multiplier=float(data.get("position_size_multiplier", 0.5)),
            stop_loss_pct=float(data.get("stop_loss_pct", 2.0)),
            take_profit_pct=float(data.get("take_profit_pct", 5.0)),
            time_horizon=data.get("time_horizon", "short"),
            explanation=data.get("explanation", "Reasoning generated by quantized LLM"),
            inference_time_ms=0.0,
            metadata={
                "model": self.model_id,
                "backend": "ollama",
                "raw_response": (response if len(response) < MAX_RAW_RESPONSE_LEN else "truncated"),
            },
        )

    def get_model_info(self) -> dict[str, Any]:
        """Status for /info endpoint."""
        return {
            "model_type": "Ollama",
            "model_id": self.model_id,
            "is_loaded": self._is_loaded,
            "endpoint": self.base_url,
            "estimated_memory_mb": 0,  # Memory offloaded to Ollama process
            "decision_count": self._decision_count,
        }
