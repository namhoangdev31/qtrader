from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from decimal import Decimal

import polars as pl

from qtrader.core.event_bus import EventBus
from qtrader.core.events import MarketEvent, SignalEvent, SignalPayload, SystemEvent, SystemPayload
from qtrader.ml.regime import RegimeDetector
from qtrader.ml.registry import ModelRegistry
from qtrader.ml.rotation import ModelRotator

__all__ = ["AutonomousLoop"]
log = logging.getLogger("qtrader.ml.autonomous")
DataProvider = Callable[[], Awaitable[pl.DataFrame]]


@dataclass(slots=True)
class AutonomousLoop:
    detector: RegimeDetector
    rotator: ModelRotator
    registry: ModelRegistry
    bus: EventBus
    interval_s: int = 3600
    drift_threshold: float = 0.25
    _last_regime: int | None = field(init=False, default=None)
    _last_run_ts: float = field(init=False, default=0.0)

    async def run_step(self, recent_data: pl.DataFrame, feature_cols: list[str]) -> None:
        try:
            (regime_id, confidence) = self.detector.current_regime_confidence(
                recent_data, feature_cols
            )
        except Exception as exc:
            log.error("Regime detection failed", exc_info=exc)
            return
        regime_changed = self._last_regime is not None and regime_id != self._last_regime
        self._last_regime = regime_id
        if regime_changed:
            event = SignalEvent(
                source="AutonomousLoop",
                payload=SignalPayload(
                    symbol="__regime__",
                    signal_type="REGIME_CHANGE",
                    strength=Decimal(str(confidence)),
                    metadata={
                        "regime": regime_id,
                        "confidence": confidence,
                        "action": "regime_change",
                    },
                ),
            )
            await self.bus.publish(event)
            log.info("Regime change: %s (conf: %.3f)", regime_id, confidence)
        target_model_id = self.rotator.on_regime_change(regime_id)
        if target_model_id is not None:
            self.registry.log_model_iteration(
                model_name="regime_rotation",
                model={"model_id": target_model_id},
                features=feature_cols,
                params={"regime_id": regime_id},
                metrics={"confidence": confidence},
                tags={"rotation_event": "true"},
            )

    async def on_market_data(
        self, event: MarketEvent, get_data_func: DataProvider, feature_cols: list[str]
    ) -> None:
        current_ts = asyncio.get_event_loop().time()
        if current_ts - self._last_run_ts < self.interval_s:
            return
        try:
            recent_data = await get_data_func()
            await self.run_step(recent_data, feature_cols)
            self._last_run_ts = current_ts
        except Exception as exc:
            log.error("Autonomous market data handler failed", exc_info=exc)

    async def on_drift(self, event: SystemEvent) -> None:
        drift_score = event.payload.metadata.get("drift_score", 0.0)
        symbol = event.payload.metadata.get("symbol", "unknown")
        if drift_score > self.drift_threshold:
            log.warning(
                "[ML] Significant drift detected (%.3f > %.3f). Triggering retrain...",
                drift_score,
                self.drift_threshold,
            )
            retrain_event = SystemEvent(
                source="AutonomousLoop",
                trace_id=event.trace_id,
                payload=SystemPayload(
                    action="MODEL_RETRAIN",
                    reason=f"Drift score {drift_score:.3f} exceeded threshold",
                    metadata={
                        "symbol": symbol,
                        "model_id": str(self._last_regime or "active"),
                        "drift_score": drift_score,
                    },
                ),
            )
            await self.bus.publish(retrain_event)
            self.registry.log_model_iteration(
                model_name="auto_retrain_trigger",
                model={"status": "pending"},
                features=[],
                params={"trigger": "drift"},
                metrics={"drift_score": drift_score},
                tags={"reason": "drift"},
            )


if __name__ == "__main__":
    from qtrader.ml.registry import ModelRegistry
    from qtrader.ml.rotation import ModelRotator

    _detector = RegimeDetector()
    _rotator = ModelRotator()
    _registry = ModelRegistry(experiment_name="test_autonomous")
    _bus = EventBus()
    _loop = AutonomousLoop(
        detector=_detector, rotator=_rotator, registry=_registry, bus=_bus, interval_s=1
    )
    if not isinstance(_loop, AutonomousLoop):
        raise TypeError("Failed to initialize AutonomousLoop properly")
