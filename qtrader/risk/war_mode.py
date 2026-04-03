"""Capital Preservation Mode (War Mode) — Standash §6.4.

When activated during extreme market conditions, the system:
1. Stops opening new positions
2. Reduces portfolio exposure
3. Only allows hedging or unwinding existing positions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from qtrader.core.events import EventType, SystemEvent, SystemPayload

_LOG = logging.getLogger("qtrader.risk.war_mode")


class WarModeState(str, Enum):
    """War Mode lifecycle states."""

    NORMAL = "NORMAL"
    ACTIVATING = "ACTIVATING"
    ACTIVE = "ACTIVE"
    DEACTIVATING = "DEACTIVATING"


@dataclass(slots=True)
class WarModeConfig:
    """Configuration for War Mode activation thresholds."""

    # Trigger thresholds
    dd_trigger_pct: float = 0.15  # Activate at 15% drawdown
    daily_loss_trigger: float = 50_000.0  # Activate at $50K daily loss
    volatility_trigger: float = 3.0  # Activate when vol > 3x normal
    anomaly_trigger: float = 0.95  # Activate on 95% anomaly intensity

    # Exposure limits during War Mode
    max_exposure_pct: float = 0.50  # Max 50% of capital exposed
    max_position_pct: float = 0.02  # Max 2% per symbol
    max_leverage: float = 1.0  # No leverage allowed
    allow_new_positions: bool = False  # Block all new positions
    allow_hedging: bool = True  # Allow hedging only
    allow_unwind: bool = True  # Allow position unwinding


@dataclass(slots=True)
class WarModeStatus:
    """Current War Mode status."""

    state: WarModeState = WarModeState.NORMAL
    activated_at: float = 0.0
    activation_reason: str = ""
    current_exposure_pct: float = 0.0
    positions_to_unwind: list[str] = field(default_factory=list)
    actions_taken: list[str] = field(default_factory=list)

    @property
    def is_active(self) -> bool:
        return self.state in (WarModeState.ACTIVATING, WarModeState.ACTIVE)


class WarModeEngine:
    """Capital Preservation Mode engine.

    Implements Standash §6.4:
    - Auto-activate on extreme market conditions
    - Stop new positions, reduce exposure, only hedge/unwind
    - Gradual recovery when conditions normalize
    """

    def __init__(self, config: WarModeConfig | None = None) -> None:
        self.config = config or WarModeConfig()
        self.status = WarModeStatus()
        self._activation_count: int = 0

    def evaluate_activation(
        self,
        drawdown_pct: float,
        daily_loss: float,
        volatility_ratio: float,
        anomaly_intensity: float,
    ) -> bool:
        """Evaluate whether War Mode should be activated.

        Args:
            drawdown_pct: Current portfolio drawdown as fraction (e.g., 0.15 = 15%).
            daily_loss: Absolute daily PnL loss in USD.
            volatility_ratio: Current vol / normal vol ratio.
            anomaly_intensity: Market anomaly score [0, 1].

        Returns:
            True if War Mode was activated.
        """
        if self.status.is_active:
            return False

        reasons: list[str] = []

        if drawdown_pct >= self.config.dd_trigger_pct:
            reasons.append(f"Drawdown {drawdown_pct:.1%} >= {self.config.dd_trigger_pct:.1%}")
        if daily_loss >= self.config.daily_loss_trigger:
            reasons.append(
                f"Daily loss ${daily_loss:,.0f} >= ${self.config.daily_loss_trigger:,.0f}"
            )
        if volatility_ratio >= self.config.volatility_trigger:
            reasons.append(
                f"Vol ratio {volatility_ratio:.1f}x >= {self.config.volatility_trigger:.1f}x"
            )
        if anomaly_intensity >= self.config.anomaly_trigger:
            reasons.append(f"Anomaly {anomaly_intensity:.2f} >= {self.config.anomaly_trigger:.2f}")

        if reasons:
            self._activate("; ".join(reasons))
            return True

        return False

    def _activate(self, reason: str) -> None:
        """Activate War Mode."""
        self.status.state = WarModeState.ACTIVATING
        self.status.activated_at = self._now()
        self.status.activation_reason = reason
        self._activation_count += 1

        actions = [
            "BLOCK_NEW_POSITIONS",
            "REDUCE_EXPOSURE",
            "ENABLE_HEDGING_ONLY",
            "NOTIFY_RISK_TEAM",
        ]
        self.status.actions_taken = actions

        _LOG.critical(
            f"[WAR MODE] ACTIVATED | Reason: {reason} | "
            f"Activation #{self._activation_count} | Actions: {actions}"
        )

        # Transition to fully active
        self.status.state = WarModeState.ACTIVE

    def evaluate_deactivation(
        self,
        drawdown_pct: float,
        daily_loss: float,
        volatility_ratio: float,
        anomaly_intensity: float,
    ) -> bool:
        """Evaluate whether War Mode can be deactivated.

        All triggers must be below 50% of activation thresholds for deactivation.
        """
        if not self.status.is_active:
            return False

        safe_drawdown = drawdown_pct < (self.config.dd_trigger_pct * 0.5)
        safe_loss = daily_loss < (self.config.daily_loss_trigger * 0.5)
        safe_vol = volatility_ratio < (self.config.volatility_trigger * 0.5)
        safe_anomaly = anomaly_intensity < (self.config.anomaly_trigger * 0.5)

        if safe_drawdown and safe_loss and safe_vol and safe_anomaly:
            self._deactivate()
            return True

        return False

    def _deactivate(self) -> None:
        """Deactivate War Mode and return to normal operations."""
        self.status.state = WarModeState.DEACTIVATING
        _LOG.info("[WAR MODE] DEACTIVATING | Market conditions normalized")

        # Reset status
        self.status.state = WarModeState.NORMAL
        self.status.activation_reason = ""
        self.status.actions_taken = []
        self.status.positions_to_unwind = []

        _LOG.info("[WAR MODE] NORMAL operations resumed")

    def check_order_allowed(
        self,
        symbol: str,
        side: str,
        is_hedge: bool,
        is_unwind: bool,
    ) -> tuple[bool, str]:
        """Check if an order is allowed under current War Mode state.

        Args:
            symbol: Trading symbol.
            side: BUY or SELL.
            is_hedge: Whether this is a hedging order.
            is_unwind: Whether this is unwinding an existing position.

        Returns:
            (allowed, reason) tuple.
        """
        if not self.status.is_active:
            return True, "Normal operations"

        if is_hedge and self.config.allow_hedging:
            return True, "War Mode: Hedging allowed"

        if is_unwind and self.config.allow_unwind:
            return True, "War Mode: Unwind allowed"

        if not self.config.allow_new_positions:
            return (
                False,
                f"War Mode: New positions blocked (reason: {self.status.activation_reason})",
            )

        return True, "Normal operations"

    def get_status(self) -> dict[str, Any]:
        """Return current War Mode status for monitoring."""
        return {
            "state": self.status.state.value,
            "is_active": self.status.is_active,
            "activated_at": self.status.activated_at,
            "activation_reason": self.status.activation_reason,
            "activation_count": self._activation_count,
            "current_exposure_pct": self.status.current_exposure_pct,
            "actions_taken": self.status.actions_taken,
            "config": {
                "dd_trigger_pct": self.config.dd_trigger_pct,
                "daily_loss_trigger": self.config.daily_loss_trigger,
                "volatility_trigger": self.config.volatility_trigger,
                "max_exposure_pct": self.config.max_exposure_pct,
                "max_position_pct": self.config.max_position_pct,
                "max_leverage": self.config.max_leverage,
            },
        }

    @staticmethod
    def _now() -> float:
        import time

        return time.time()
