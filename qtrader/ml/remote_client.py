from __future__ import annotations
import logging
import time
from typing import Any
import aiohttp
from qtrader.ml.atomic_trio import PipelineResult

logger = logging.getLogger("qtrader.ml.remote_client")
HTTP_OK = 200
DEFAULT_TIMEOUT = 5.0
PREDICT_TIMEOUT = 180.0


class RemoteAtomicTrioPipeline:
    def __init__(self, base_url: str = "http://qt-ml-engine:8001") -> None:
        self.base_url = base_url.rstrip("/")
        self._run_count = 0
        self._model_info: dict[str, Any] = {}
        logger.info(f"[REMOTE_ML] Initialized client for {self.base_url}")

    async def _initialize(self) -> None:
        if self._model_info:
            return
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/info", timeout=DEFAULT_TIMEOUT) as resp:
                    if resp.status == HTTP_OK:
                        self._model_info = await resp.json()
                        logger.info(
                            "[REMOTE_ML] Connected to %s | Info: %s runs",
                            self.base_url,
                            self._model_info.get("run_count", 0),
                        )
                    else:
                        logger.warning("[REMOTE_ML] Info failed: %s", resp.status)
            except Exception as e:
                logger.error("[REMOTE_ML] Connection error: %s", e)

    async def run(
        self,
        historical_prices: list[float] | None = None,
        market_features: dict[str, float] | None = None,
        market_context: dict[str, Any] | None = None,
        system_state: dict[str, Any] | None = None,
        prediction_length: int = 10,
    ) -> PipelineResult:
        self._run_count += 1
        start_t = time.time()
        payload = {
            "historical_prices": historical_prices,
            "market_features": market_features,
            "market_context": market_context,
            "system_state": system_state,
            "prediction_length": prediction_length,
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    f"{self.base_url}/predict", json=payload, timeout=PREDICT_TIMEOUT
                ) as resp:
                    if resp.status == HTTP_OK:
                        data = await resp.json()
                        latency = (time.time() - start_t) * 1000
                        result = PipelineResult(
                            decision=data.get("decision", "HOLD"),
                            forecast_results=data.get("forecast_results"),
                            risk_results=data.get("risk_results"),
                            pipeline_latency_ms=latency,
                            forecast_latency_ms=data.get("forecast_latency_ms", 0.0),
                            risk_latency_ms=data.get("risk_latency_ms", 0.0),
                            decision_latency_ms=data.get("decision_latency_ms", 0.0),
                            model_info=data.get("model_info", {}),
                        )
                        return result
                    else:
                        error_text = await resp.text()
                        logger.error(f"[REMOTE_ML] Prediction failed ({resp.status}): {error_text}")
            except Exception as e:
                logger.error(f"[REMOTE_ML] Prediction connection error: {e!r}")
        latency = (time.time() - start_t) * 1000
        return PipelineResult(
            decision={"action": "HOLD", "reasoning": "Remote connection failed"},
            pipeline_latency_ms=latency,
            model_info={"error": "Remote connection failed"},
        )

    def get_pipeline_info(self) -> dict[str, Any]:
        return self._model_info or {"status": "connecting", "base_url": self.base_url}
