from __future__ import annotations
import json
import logging
import time
from typing import Any
import aiohttp
import numpy as np
from qtrader.ml.chronos_adapter import ForecastResult

logger = logging.getLogger("qtrader.ml.ollama_forecast")
HTTP_OK = 200


class OllamaForecastAdapter:
    def __init__(self, model_id: str, base_url: str, timeout_seconds: int = 180) -> None:
        self.model_id = model_id
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self._is_loaded = True

    async def predict(
        self, historical_prices: list[float] | np.ndarray, prediction_length: int = 10
    ) -> ForecastResult:
        prices = np.asarray(historical_prices, dtype=np.float64)
        start_time = time.time()
        prompt = f'IMPORTANT: Response must be a single, valid JSON object only. No conversational filler. Follow this schema exactly:\n\nInput History: {prices.tolist()[-50:]}\nPrediction Length: {prediction_length}\n{{"forecast": [val1, val2, ...]}}\n\nResponse:'
        try:
            response_text = await self._generate(prompt)
            forecast_data = self._parse_forecast(response_text)
            mean = np.array(forecast_data)
            vol = np.std(prices) * 0.1
            lower_bound = mean - vol
            upper_bound = mean + vol
            q05 = mean - 2 * vol
            q95 = mean + 2 * vol
        except Exception as e:
            logger.error(f"[OLLAMA_FORECAST] Inference failed: {e}")
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
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 512},
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
            start_idx = clean.find("{")
            end_idx = clean.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean = clean[start_idx : end_idx + 1]
            if clean.startswith("{") and (not clean.endswith("}")):
                clean += '"]}' if '["' in clean or '":' in clean else "}"
            data = json.loads(clean)
            if "forecast" in data and isinstance(data["forecast"], list):
                return [float(x) for x in data["forecast"]]
            for val in data.values():
                if isinstance(val, list) and len(val) > 0:
                    try:
                        return [float(x) for x in val]
                    except (ValueError, TypeError):
                        continue
            raise KeyError("No valid numeric array found in JSON")
        except Exception as e:
            snippet = text[:100].replace("\n", " ")
            raise ValueError(f"Failed to parse forecast from: {snippet}... Error: {e}")

    def _fallback_forecast(self, prices: np.ndarray, length: int) -> np.ndarray:
        if len(prices) < 2:
            return np.full(length, prices[0] if len(prices) > 0 else 0)
        trend = (prices[-1] - prices[0]) / len(prices)
        return np.array([prices[-1] + trend * (i + 1) for i in range(length)])

    def get_model_info(self) -> dict[str, Any]:
        return {"model_id": self.model_id, "adapter": "OllamaForecast", "is_loaded": True}
