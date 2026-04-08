"""Ollama Forecast Adapter — Fast LLM-based Price Projection.

Uses lightweight LLMs (like Llama 3.2 1B) to perform rapid trend forecasting.
Optimized for Mac M4 via Ollama.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import aiohttp
import numpy as np

from qtrader.ml.chronos_adapter import ForecastResult

logger = logging.getLogger("qtrader.ml.ollama_forecast")

HTTP_OK = 200

class OllamaForecastAdapter:
    """Ollama Forecast Adapter.

    Uses a general LLM via Ollama to predict future price points.
    """

    def __init__(
        self,
        model_id: str,
        base_url: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._is_loaded = True # Assume loaded as orchestrator checks

    async def predict(
        self,
        historical_prices: list[float] | np.ndarray,
        prediction_length: int = 10,
    ) -> ForecastResult:
        """Generate forecast using LLM reasoning."""
        prices = np.asarray(historical_prices, dtype=np.float64)
        start_time = time.time()

        # Build prompt for forecasting
        prompt = (
            "System: Act as a financial time-series forecaster. "
            "Given a sequence of historical prices, predict the next values in the sequence. "
            "Return ONLY a JSON object containing a 'forecast' key with a list of predicted numbers.\n\n"
            f"Input History: {prices.tolist()[-50:]}\n"
            f"Prediction Length: {prediction_length}\n"
            "JSON Template: {\"forecast\": [val1, val2, ...]}\n"
            "Response:"
        )

        try:
            response_text = await self._generate(prompt)
            forecast_data = self._parse_forecast(response_text)
            
            mean = np.array(forecast_data)
            # Simple probabilistic bounds for compatibility
            vol = np.std(prices) * 0.1
            lower_bound = mean - vol
            upper_bound = mean + vol
            q05 = mean - 2 * vol
            q95 = mean + 2 * vol

        except Exception as e:
            logger.error(f"[OLLAMA_FORECAST] Inference failed: {e}")
            # Fallback: simple drift
            mean = self._fallback_forecast(prices, prediction_length)
            lower_bound = mean * 0.99
            upper_bound = mean * 1.01
            q05 = mean * 0.98
            q95 = mean * 1.02

        inference_time_ms = (time.time() - start_time) * 1000

        return ForecastResult(
            mean=np.asarray(mean),
            lower_bound=np.asarray(lower_bound),
            upper_bound=np.asarray(upper_bound),
            prediction_length=prediction_length,
            context_length=len(prices),
            inference_time_ms=inference_time_ms,
            model_size=self.model_id,
            quantile_05=np.asarray(q05),
            quantile_95=np.asarray(q95),
        )

    async def _generate(self, prompt: str) -> str:
        payload = {
            "model": self.model_id,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 128},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/generate", json=payload, timeout=self.timeout_seconds
            ) as resp:
                if resp.status != HTTP_OK:
                    raise RuntimeError(f"Ollama error: {resp.status}")
                data = await resp.json()
                return str(data.get("response", ""))

    def _parse_forecast(self, text: str) -> list[float]:
        try:
            clean = text.strip()
            if "```json" in clean:
                clean = clean.split("```json")[-1].split("```")[0].strip()
            data = json.loads(clean)
            return [float(x) for x in data["forecast"]]
        except Exception:
            raise ValueError(f"Failed to parse forecast from: {text[:50]}...")

    def _fallback_forecast(self, prices: np.ndarray, length: int) -> np.ndarray:
        if len(prices) < 2:
            return np.full(length, prices[0] if len(prices) > 0 else 0)
        trend = (prices[-1] - prices[0]) / len(prices)
        return np.array([prices[-1] + trend * (i + 1) for i in range(length)])

    def get_model_info(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "adapter": "OllamaForecast",
            "is_loaded": True
        }
