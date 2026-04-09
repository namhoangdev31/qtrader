from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from qtrader.execution.algos.base import ChildOrder

if TYPE_CHECKING:
    from qtrader.core.events import OrderEvent
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.strategy.slicing")


@dataclass(slots=True)
class SlicingState:
    remaining_qty: float
    elapsed_time_sec: float
    total_duration_sec: float
    last_update: datetime


class AdaptiveSlicer:
    def __init__(self, config: ExecutionConfig) -> None:
        slicing_cfg = getattr(config, "routing", {}).get("slicing", {})
        self._max_participation = float(slicing_cfg.get("max_participation_rate", 0.1))
        self._urgency_sensitivity = float(slicing_cfg.get("urgency_sensitivity", 1.5))

    def generate_slice(
        self, order: OrderEvent, state: SlicingState, signals: dict[str, float]
    ) -> ChildOrder | None:
        try:
            time_fraction = state.elapsed_time_sec / max(1.0, state.total_duration_sec)
            qty_fraction = (order.quantity - state.remaining_qty) / max(1.0, order.quantity)
            schedule_deviation = time_fraction - qty_fraction
            imbalance = signals.get("imbalance", 0.0)
            toxicity = signals.get("toxicity", 0.5)
            spread_ratio = signals.get("spread_ratio", 1.0)
            side_multiplier = 1.0 if order.action.upper() == "BUY" else -1.0
            urgency = 1.0 + imbalance * side_multiplier * self._urgency_sensitivity
            toxic_threshold = 0.7
            spread_threshold = 1.2
            if toxicity > toxic_threshold:
                urgency *= 0.1
            elif spread_ratio > spread_threshold:
                urgency *= 0.4
            base_slice_pct = 0.05
            target_slice = order.quantity * base_slice_pct * urgency * (1.0 + schedule_deviation)
            target_slice = min(target_slice, state.remaining_qty)
            market_vol = signals.get("level_volume", 0.0)
            if market_vol > 0:
                max_qty = market_vol * self._max_participation
                target_slice = min(target_slice, max_qty)
            min_executable_qty = 1e-08
            if target_slice < min_executable_qty:
                return None
            return ChildOrder(
                parent_id=order.order_id or "adaptive_slicer",
                symbol=order.symbol,
                side=order.action,
                quantity=float(target_slice),
                price=signals.get("microprice"),
                scheduled_at=datetime.now().timestamp(),
            )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("AdaptiveSlicer: failed to generate slice", exc_info=True)
            return None
