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
    def __init__(
        self, model_id: str | None = None, base_url: str | None = None, timeout_seconds: int = 180
    ) -> None:
        self.model_id = model_id or os.getenv("OLLAMA_MODEL_DECISION", "llama3.2:1b")
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.timeout_seconds = timeout_seconds
        self._is_loaded = False
        self._decision_count: int = 0
        self._embed_count: int = 0

    async def _check_ready(self) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags", timeout=TIMEOUT_CONNECT
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
        rag_context: list[dict[str, Any]] | None = None,
    ) -> TradingDecision:
        start_time = time.time()
        self._decision_count += 1
        prompt = self._build_prompt(
            chronos_forecast, tabpfn_risk, market_context, system_state, rag_context
        )
        try:
            response_text = await self._generate(prompt)
            decision = self._parse_response(response_text, chronos_forecast, tabpfn_risk)
        except Exception as e:
            logger.error(f"[OLLAMA] Decision inference failed: {e}")
            decision = TradingDecision(
                action=DecisionAction.HOLD,
                confidence=0.0,
                reasoning=f"Ollama failure: {e}",
                risk_adjustment=1.0,
                position_size_multiplier=0.0,
                stop_loss_pct=2.0,
                take_profit_pct=5.0,
                time_horizon="short",
                explanation=f"Emergency fallback (Timeout/Error in AI Engine: {e})",
                inference_time_ms=0.0,
            )
        decision.inference_time_ms = (time.time() - start_time) * 1000
        return decision

    async def _generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 512},
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
        rag_context: list[dict[str, Any]] | None = None,
    ) -> str:
        instruct = (
            "System: Act as an institutional quantitative trading engine. "
            "Analyze inputs and provide a trading decision in strict JSON format.\n"
        )
        if rag_context:
            instruct += (
                "RAG INSTITUTIONAL MEMORY:\n"
                "The following 'Elite Exemplars' (past success) or "
                "'Forensic Interventions' (live human directives) were retrieved:\n"
            )
            for i, match in enumerate(rag_context, 1):
                role = (
                    "FORENSIC INTERVENTION"
                    if match.get("regime") == "forensic_intervention"
                    else "HISTORICAL SUCCESS"
                )
                instruct += (
                    f"Match {i} [{role}] (Similarity: {match['similarity']:.2f}):\n"
                    f"  Parameters/Context: {json.dumps(match['parameters'])}\n"
                    f"  Expert Note: {match['notes']}\n"
                )
            instruct += (
                "\nIMPORTANT: Prioritize 'FORENSIC INTERVENTION' as these are immediate "
                "human directives for the current market state. "
                "Use them to override or bias your decision.\n"
            )
        instruct += (
            "IMPORTANT: Response must be a single, valid JSON object only. "
            "No conversational filler, no markdown blocks, no prefix/suffix. "
            "Follow this schema exactly:\n\n"
            '{"action": "BUY/SELL/HOLD/HEDGE", "confidence": float, "reasoning": string, '
            '"risk_adjustment": float, "position_size_multiplier": float, '
            '"stop_loss_pct": float, "take_profit_pct": float, '
            '"time_horizon": "short/medium/long", "explanation": string,'
            '"config_overrides": {"MIN_CONFIDENCE": float, "STOP_LOSS_PCT": float, '
            '"TAKE_PROFIT_PCT": float}}\n\n'
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
        try:
            clean = response.strip()
            start_idx = clean.find("{")
            end_idx = clean.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean = clean[start_idx : end_idx + 1]
            if clean.startswith("{") and (not clean.endswith("}")):
                clean += '"}' if '":' in clean else "}"
            data = json.loads(clean)
        except Exception as e:
            logger.warning(f"[OLLAMA] Failed to parse JSON from: {response[:100]}... Error: {e}")
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
                "raw_response": response if len(response) < MAX_RAW_RESPONSE_LEN else "truncated",
                "config_overrides": data.get("config_overrides", {}),
            },
        )

    async def embed(self, text: str) -> list[float]:
        self._embed_count += 1
        payload = {"model": self.model_id, "input": text}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/embed", json=payload, timeout=self.timeout_seconds
            ) as resp:
                if resp.status != HTTP_OK:
                    text = await resp.text()
                    logger.error(f"[OLLAMA_EMBED] API returned {resp.status}: {text}")
                    return []
                data = await resp.json()
                return data.get("embeddings", [[]])[0]

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model_type": "Ollama (RAG-Enabled)",
            "model_id": self.model_id,
            "is_loaded": self._is_loaded,
            "endpoint": self.base_url,
            "estimated_memory_mb": 0,
            "decision_count": self._decision_count,
            "embed_count": self._embed_count,
        }
