from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import polars as pl

from qtrader.core.bus import EventBus
from qtrader.core.event import EventType, SignalEvent
from qtrader.ml.regime import RegimeDetector
from qtrader.ml.registry import ModelRegistry
from qtrader.ml.rotation import ModelRotator

__all__ = ["AutonomousLoop"]

log = logging.getLogger(__name__)


DataProvider = Callable[[], Awaitable[pl.DataFrame]]


@dataclass(slots=True)
class AutonomousLoop:
    """Production auto-retraining loop that publishes regime changes.

    On each step:
      1. Predict current regime and posterior probabilities.
      2. Detect regime changes and publish a ``SignalEvent`` to the EventBus.
      3. Delegate to ``ModelRotator`` to select a target model.
      4. Log rotations to MLflow via ``ModelRegistry``.

    Args:
        detector: Regime detector instance.
        rotator: Model rotator managing active model IDs.
        registry: MLflow-backed model registry.
        bus: EventBus used to publish regime-change signals.
        interval_s: Interval between iterations in seconds.
    """

    detector: RegimeDetector
    rotator: ModelRotator
    registry: ModelRegistry
    bus: EventBus
    interval_s: int = 3600
    _last_regime: int | None = field(init=False, default=None)

    async def run_step(self, recent_data: pl.DataFrame, feature_cols: list[str]) -> None:
        """Execute one autonomous step.

        Args:
            recent_data: Recent market data as a Polars DataFrame.
            feature_cols: Columns to use as regime features.
        """
        try:
            regime_id, confidence = self.detector.current_regime_confidence(
                recent_data, feature_cols
            )
        except Exception as exc:
            log.error("Regime detection failed", exc_info=exc)
            return

        regime_changed = self._last_regime is not None and regime_id != self._last_regime
        self._last_regime = regime_id

        if regime_changed:
            event = SignalEvent(
                type=EventType.SIGNAL,
                symbol="__regime__",
                signal_type="REGIME_CHANGE",
                strength=confidence,
                metadata={
                    "regime": regime_id,
                    "confidence": confidence,
                    "action": "regime_change",
                },
            )
            await self.bus.publish(event)
            log.info(
                "Regime change detected: regime=%s confidence=%.3f",
                regime_id,
                confidence,
            )

        target_model_id = self.rotator.on_regime_change(regime_id)
        if target_model_id is not None:
            log.info("Rotated to model_id=%s for regime=%s", target_model_id, regime_id)
            # Best-effort metadata logging; model artifact logging happens in training.
            try:
                self.registry.log_model_iteration(
                    model_name="regime_rotation",
                    model={"model_id": target_model_id},
                    features=feature_cols,
                    params={"regime_id": regime_id},
                    metrics={"confidence": confidence},
                    tags={"rotation_event": "true", "target_model_id": str(target_model_id)},
                )
            except Exception as exc:
                log.error("Failed to log rotation to MLflow", exc_info=exc)

    async def on_market_data(self, event: MarketDataEvent, get_data_func: DataProvider, feature_cols: list[str]) -> None:
        """Trigger one autonomous step based on market data event (zero latency)."""
        current_ts = event.timestamp.timestamp()
        
        # Check throttling if interval_s is set
        if hasattr(self, "_last_run_ts") and current_ts - self._last_run_ts < self.interval_s:
            return
            
        try:
            recent_data = await get_data_func()
            if not isinstance(recent_data, pl.DataFrame):
                raise TypeError("get_data_func must return a Polars DataFrame.")
            await self.run_step(recent_data, feature_cols)
            self._last_run_ts = current_ts
        except Exception as exc:
            log.error("Autonomous step failed", exc_info=exc)

    # loop/sleep start method removed in favor of event-driven on_market_data


if __name__ == "__main__":
    # Smoke test: construct with dummy components (no EventBus loop).
    from qtrader.ml.registry import ModelRegistry  # type: ignore[reimported]
    from qtrader.ml.rotation import ModelRotator  # type: ignore[reimported]

    _detector = RegimeDetector()
    _rotator = ModelRotator()
    _registry = ModelRegistry(experiment_name="test_autonomous")
    _bus = EventBus()
    _loop = AutonomousLoop(
        detector=_detector,
        rotator=_rotator,
        registry=_registry,
        bus=_bus,
        interval_s=1,
    )
    assert isinstance(_loop, AutonomousLoop)

