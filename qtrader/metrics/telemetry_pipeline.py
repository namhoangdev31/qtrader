from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from qtrader.core.metrics import metrics


class TelemetryPipeline:
    """
    Background worker for aggregating system metrics and persisting them to the audit log.
    Provides the quantitative baseline for Phase -1.5 performance validation.
    """

    def __init__(self, interval_seconds: float = 5.0, output_path: str = "qtrader/metrics/metrics_registry.json") -> None:
        self.interval = interval_seconds
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Initialize and start the telemetry background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"TELEMETRY_PIPELINE | Started background worker (Interval: {self.interval}s)")

    async def stop(self) -> None:
        """Gracefully stop the telemetry background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("TELEMETRY_PIPELINE | Stopped background worker")

    async def _run_loop(self) -> None:
        """Main execution loop for metrics aggregation and persistence."""
        while self._running:
            try:
                await asyncio.sleep(self.interval)
                await self._persist_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TELEMETRY_PIPELINE_FAILURE | {e}")

    async def _persist_snapshot(self) -> None:
        """Capture a metrics snapshot and write to disk in JSON format."""
        snapshot = await metrics.snapshot()
        snapshot["last_updated"] = datetime.now(timezone.utc).isoformat()
        
        # Atomically write to disk (temp file + rename)
        tmp_path = self.output_path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w") as f:
                json.dump(snapshot, f, indent=2)
            os.replace(tmp_path, self.output_path)
        except Exception as e:
            logger.error(f"TELEMETRY_STORAGE_FAILURE | Failed to write {self.output_path}: {e}")


# Singleton instance for high-frequency telemetry integration
telemetry_pipeline = TelemetryPipeline()
