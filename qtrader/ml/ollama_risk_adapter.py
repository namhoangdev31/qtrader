from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import aiohttp

from qtrader.ml.types import RiskClassificationResult

logger = logging.getLogger("qtrader.ml.ollama_risk")
HTTP_OK = 200
TIMEOUT_CONNECT = 5


class OllamaRiskAdapter:
    def __init__(
        self, model_id: str | None = None, base_url: str | None = None, timeout_seconds: int = 180
    ) -> None:
        self.model_id = model_id or os.getenv("OLLAMA_MODEL_RISK", "qwen3-embedding:0.6b")
        self.base_url = base_url or os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.timeout_seconds = timeout_seconds
        self._is_loaded = False
        self._classify_count: int = 0

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
            logger.warning(f"[OLLAMA_RISK] Not ready at {self.base_url}: {e}")
        return False

    async def classify(
        self, features: dict[str, float], feature_names: list[str] | None = None
    ) -> RiskClassificationResult:
        start_time = time.time()
        self._classify_count += 1
        prompt = self._build_risk_prompt(features)
        try:
            response_text = await self._generate(prompt)
            result = self._parse_risk_response(response_text)
        except Exception as e:
            logger.error(f"[OLLAMA_RISK] Inference failed: {e}")
            result = RiskClassificationResult(
                class_label="WARNING",
                probabilities={"SAFE": 0.2, "WARNING": 0.6, "DANGER": 0.2},
                confidence=0.5,
                inference_time_ms=0.0,
                risk_score=0.5,
                feature_importance={},
            )
        result.inference_time_ms = (time.time() - start_time) * 1000
        return result

    async def _generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 256},
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

    def _build_risk_prompt(self, features: dict[str, float]) -> str:
        instruct = (
            "System: Act as an institutional quantitative risk analyst. "
            "Analyze market features and classify current market risk into: "
            "SAFE, WARNING, or DANGER.\n"
            "Classification Rules:\n"
            "- SAFE: Trending market, stable volatility, low spread.\n"
            "- WARNING: High volatility, abnormal volume, or widening spreads.\n"
            "- DANGER: Extreme volatility, price crashes, or severe order imbalance.\n\n"
            "IMPORTANT: Response must be a single, valid JSON object only. "
            "No conversational filler. Follow this schema exactly:\n\n"
            '{"class_label": "SAFE/WARNING/DANGER", "confidence": float, '
            '"risk_score": float, "reasoning": string}\n\n'
        )
        return f"{instruct}Market Features:\n{json.dumps(features)}\n\nOutput JSON:"

    def _parse_risk_response(self, response: str) -> RiskClassificationResult:
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
            logger.warning(f"[OLLAMA_RISK] Failed to parse JSON: {response[:100]}... Error: {e}")
            data = {}
        label = data.get("class_label", "WARNING").upper()
        if label not in ["SAFE", "WARNING", "DANGER"]:
            label = "WARNING"
        conf = float(data.get("confidence", 0.5))
        score = float(data.get("risk_score", 0.5))
        if label == "SAFE":
            probs = {"SAFE": conf, "WARNING": (1 - conf) * 0.7, "DANGER": (1 - conf) * 0.3}
        elif label == "DANGER":
            probs = {"SAFE": (1 - conf) * 0.2, "WARNING": (1 - conf) * 0.3, "DANGER": conf}
        else:
            probs = {"SAFE": (1 - conf) * 0.4, "WARNING": conf, "DANGER": (1 - conf) * 0.4}
        return RiskClassificationResult(
            class_label=label,
            probabilities=probs,
            confidence=conf,
            inference_time_ms=0.0,
            risk_score=score,
            feature_importance={},
        )

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model_type": "Ollama (Risk)",
            "model_id": self.model_id,
            "is_loaded": self._is_loaded,
            "endpoint": self.base_url,
            "estimated_memory_mb": 0,
            "classify_count": self._classify_count,
        }
