"""Failsafe fallback engine for graceful degradation on system failure.

Implements the process logic:
    on failure:
        switch to HOLD
        reduce exposure

Provides deterministic fallback strategies that ensure the system never enters
an uncontrolled state. Subscribes to ERROR and RISK events from the EventBus
and autonomously transitions the trading system to safe mode.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum, auto
from typing import Any

from qtrader.core.event import ErrorEvent, EventType, RiskEvent
from qtrader.core.event_bus import EventBus

_LOG = logging.getLogger("qtrader.risk.fallback_engine")


class FallbackMode(Enum):
    """System degradation levels."""
    NORMAL = auto()       # Full trading capacity
    REDUCED = auto()      # Reduced position sizing, no new entries
    HOLD = auto()         # Hold current positions, no new orders
    EMERGENCY = auto()    # Flatten all positions and halt


@dataclass
class FallbackState:
    """Current fallback state snapshot."""
    mode: FallbackMode = FallbackMode.NORMAL
    reason: str = ""
    triggered_at: datetime | None = None
    exposure_multiplier: float = 1.0  # 1.0 = full, 0.5 = half, 0.0 = none
    consecutive_errors: int = 0
    error_log: list[str] = field(default_factory=list)


class FallbackEngine:
    """Event-driven failsafe system.

    Subscribes to:
      - EventType.ERROR: Tracks consecutive errors, escalates degradation
      - EventType.RISK: Reacts to risk limit breaches

    Fallback escalation:
      - 1-2 errors  → REDUCED (exposure_multiplier = 0.5)
      - 3-4 errors  → HOLD    (exposure_multiplier = 0.0, no new orders)
      - 5+  errors  → EMERGENCY (flatten all, halt trading)

    Recovery:
      - After a configurable cooldown with no errors, the system
        de-escalates one level at a time.
    """

    ERROR_THRESHOLD_REDUCED: int = 2
    ERROR_THRESHOLD_HOLD: int = 4
    ERROR_THRESHOLD_EMERGENCY: int = 5
    COOLDOWN_SECONDS: float = 300.0  # 5 minutes between de-escalation steps

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.state = FallbackState()
        self._last_error_time: float = 0.0
        self._last_deescalation: float = 0.0

    async def start(self) -> None:
        """Subscribe to relevant events."""
        self.event_bus.subscribe(EventType.ERROR, self._on_error)
        self.event_bus.subscribe(EventType.RISK, self._on_risk)
        _LOG.info("FallbackEngine started in NORMAL mode")

    def get_exposure_multiplier(self) -> float:
        """Return the current exposure multiplier for position sizing.

        Downstream components should multiply their target size by this value
        to respect the current fallback mode.
        """
        return self.state.exposure_multiplier

    def get_state(self) -> FallbackState:
        """Return a snapshot of the current fallback state."""
        return self.state

    def is_trading_allowed(self) -> bool:
        """Return whether new order submissions are allowed."""
        return self.state.mode in (FallbackMode.NORMAL, FallbackMode.REDUCED)

    async def _on_error(self, event: ErrorEvent) -> None:
        """Handle an error event: escalate fallback if needed."""
        self.state.consecutive_errors += 1
        self._last_error_time = asyncio.get_event_loop().time()

        error_summary = f"[{event.source}] {event.message} (severity={event.severity})"
        self.state.error_log.append(error_summary)
        # Keep log bounded
        if len(self.state.error_log) > 100:
            self.state.error_log.pop(0)

        _LOG.warning(
            f"FallbackEngine error #{self.state.consecutive_errors}: {error_summary}"
        )

        # Escalation logic
        if event.severity == "CRITICAL":
            await self._transition(FallbackMode.EMERGENCY, error_summary)
        elif self.state.consecutive_errors >= self.ERROR_THRESHOLD_EMERGENCY:
            await self._transition(FallbackMode.EMERGENCY, error_summary)
        elif self.state.consecutive_errors >= self.ERROR_THRESHOLD_HOLD:
            await self._transition(FallbackMode.HOLD, error_summary)
        elif self.state.consecutive_errors >= self.ERROR_THRESHOLD_REDUCED:
            await self._transition(FallbackMode.REDUCED, error_summary)

    async def _on_risk(self, event: RiskEvent) -> None:
        """Handle a risk event: immediate escalation to HOLD or EMERGENCY."""
        action = event.metrics.get("action", "REDUCE_EXPOSURE")
        reason = f"Risk breach on {event.symbol}: {action}"
        _LOG.warning(f"FallbackEngine risk event: {reason}")

        if action == "CANCEL_ALL_ORDERS":
            await self._transition(FallbackMode.EMERGENCY, reason)
        else:
            await self._transition(FallbackMode.HOLD, reason)

    async def _transition(self, target: FallbackMode, reason: str) -> None:
        """Transition to a new fallback mode (only escalates, never de-escalates here)."""
        if target.value <= self.state.mode.value:
            return  # Already at this level or higher

        previous = self.state.mode
        self.state.mode = target
        self.state.reason = reason
        self.state.triggered_at = datetime.utcnow()

        # Set exposure multiplier
        if target == FallbackMode.REDUCED:
            self.state.exposure_multiplier = 0.5
        elif target == FallbackMode.HOLD:
            self.state.exposure_multiplier = 0.0
        elif target == FallbackMode.EMERGENCY:
            self.state.exposure_multiplier = 0.0

        _LOG.critical(
            f"FALLBACK TRANSITION: {previous.name} → {target.name} | "
            f"Reason: {reason} | Exposure: {self.state.exposure_multiplier}"
        )

    async def try_deescalate(self) -> bool:
        """Attempt to de-escalate one level if cooldown has elapsed with no new errors.

        Should be called periodically (e.g. from heartbeat handler).

        Returns:
            True if de-escalation occurred.
        """
        if self.state.mode == FallbackMode.NORMAL:
            return False

        now = asyncio.get_event_loop().time()
        time_since_error = now - self._last_error_time
        time_since_deesc = now - self._last_deescalation

        if (
            time_since_error >= self.COOLDOWN_SECONDS
            and time_since_deesc >= self.COOLDOWN_SECONDS
        ):
            previous = self.state.mode

            if previous == FallbackMode.EMERGENCY:
                self.state.mode = FallbackMode.HOLD
                self.state.exposure_multiplier = 0.0
            elif previous == FallbackMode.HOLD:
                self.state.mode = FallbackMode.REDUCED
                self.state.exposure_multiplier = 0.5
            elif previous == FallbackMode.REDUCED:
                self.state.mode = FallbackMode.NORMAL
                self.state.exposure_multiplier = 1.0
                self.state.consecutive_errors = 0

            self._last_deescalation = now
            _LOG.info(
                f"FALLBACK DE-ESCALATION: {previous.name} → {self.state.mode.name} | "
                f"Exposure: {self.state.exposure_multiplier}"
            )
            return True

        return False
