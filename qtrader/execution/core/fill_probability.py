from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qtrader.execution.config import ExecutionConfig
_LOG = logging.getLogger("qtrader.execution.core.fill_probability")

class FillProbabilityModel:
    def __init__(self, config: ExecutionConfig) -> None:
        micro_cfg = getattr(config, "microstructure", {}).get("queue_model", {})
        self._default_intensity = float(micro_cfg.get("default_intensity", 10.0))

    def compute(
        self,
        intensity: float | None = None,
        time_horizon: float = 1.0,
        queue_pos: float | None = None,
    ) -> float:
        try:
            min_vol_epsilon = 1e-08
            q_pos = queue_pos if queue_pos is not None else 1.0
            if q_pos <= min_vol_epsilon:
                return 1.0
            lam = intensity if intensity is not None else self._default_intensity
            if lam <= 0 or time_horizon <= 0:
                return 0.0
            exponent = -(lam * time_horizon) / q_pos
            prob = float(1.0 - math.exp(exponent))
            return max(0.0, min(1.0, prob))
        except (ZeroDivisionError, OverflowError):
            return 1.0
        except Exception as e:
            logging.getLogger(__name__).warning(f"Exception in {__name__}: {e}")
            _LOG.error("FillProbabilityModel: computation failed", exc_info=True)
            return 0.0