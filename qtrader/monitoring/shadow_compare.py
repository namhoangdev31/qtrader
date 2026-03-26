import logging
from datetime import datetime, timedelta
from typing import Any

from qtrader.core.logger import logger

class ShadowCompare:
    """
    Monitoring service for real shadow trading with full simulation.
    Tracks Divergence and enforces the 'Shadow >= 7 days before live' constraint.
    """

    def __init__(self, shadow_start_time: datetime | None = None) -> None:
        self.shadow_start_time = shadow_start_time or datetime.utcnow()
        self.logger = logger.bind(module="shadow_compare")

    def track_divergence(self, live_pnl: float, shadow_pnl: float) -> dict[str, float]:
        """
        Track PnL difference:
        Divergence = |PnL_live - PnL_shadow|
        """
        divergence = abs(live_pnl - shadow_pnl)
        
        self.logger.info(
            "Tracking Divergence",
            live_pnl=live_pnl,
            shadow_pnl=shadow_pnl,
            divergence=divergence
        )
        
        return {
            "live_pnl": live_pnl,
            "shadow_pnl": shadow_pnl,
            "divergence": divergence
        }

    def can_transition_to_live(self) -> bool:
        """
        Enforce CONSTRAINT: Shadow >= 7 days before live
        """
        elapsed = datetime.utcnow() - self.shadow_start_time
        if elapsed >= timedelta(days=7):
            return True
        
        self.logger.warning(
            "Cannot transition to live. Minimum shadow period not met.",
            elapsed_days=elapsed.days,
            required_days=7
        )
        return False
