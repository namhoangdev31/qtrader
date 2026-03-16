from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from qtrader.core.config import Config

from qtrader.core.bus import EventBus
from qtrader.core.event import RiskEvent

__all__ = ["RuntimeRiskEngine"]

_LOG = logging.getLogger("qtrader.output.risk.runtime")


@dataclass(slots=True)
class RuntimeRiskEngine:
    """Real-time monitoring and safety guardrails.

    This component is intentionally lightweight and focused on process-level
    kill-switch behaviour. It is complementary to the portfolio-level
    `RealTimeRiskEngine`.

    Attributes:
        max_drawdown: Maximum allowed drawdown as a fraction of high-water mark.
        max_exposure: Maximum allowed absolute exposure in base currency.
        max_daily_loss: Maximum allowed daily loss in base currency.
        current_drawdown: Current drawdown fraction.
        current_exposure: Current exposure level.
        intraday_pnl: Accumulated PnL for the current UTC trading day.
        is_active: Whether the engine considers trading to be allowed.
    """

    max_drawdown: float = 0.1
    max_exposure: float = 1_000_000.0
    max_daily_loss: float = 5_000.0
    event_bus: EventBus | None = None

    current_drawdown: float = 0.0
    current_exposure: float = 0.0
    intraday_pnl: float = 0.0
    is_active: bool = True
    current_day: date = field(
        default_factory=lambda: datetime.now(Config.tz).date(),
    )

    def check_breach(self) -> bool:
        """Check whether any safety limits have been breached.

        Returns:
            ``True`` if a breach is detected, otherwise ``False``.
        """
        if not self.is_active:
            return False

        if self.current_drawdown > self.max_drawdown:
            _LOG.critical("Max drawdown breached (%.4f > %.4f)", self.current_drawdown, self.max_drawdown)
            return True

        if self.current_exposure > self.max_exposure:
            _LOG.warning("Max exposure breached (%.2f > %.2f)", self.current_exposure, self.max_exposure)
            return True

        if -self.intraday_pnl > self.max_daily_loss:
            _LOG.critical(
                "Max daily loss breached (%.2f > %.2f)",
                -self.intraday_pnl,
                self.max_daily_loss,
            )
            return True

        return False

    def update_intraday_pnl(self, pnl_delta: float, now: datetime | None = None) -> None:
        """Update intraday PnL, resetting at UTC midnight boundaries.

        Args:
            pnl_delta: Incremental PnL to add to the current day.
            now: Optional timestamp; defaults to current UTC time.
        """
        if now is None:
            now = datetime.now(Config.tz)
        today = now.date()
        if today != self.current_day:
            self.current_day = today
            self.intraday_pnl = 0.0
        self.intraday_pnl += pnl_delta

    def trigger_kill_switch(self) -> RiskEvent:
        """Stop trading activities and request order cancellation.

        Returns:
            A `RiskEvent` instructing all open orders to be cancelled.
        """
        self.is_active = False
        metadata: dict[str, Any] = {
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "current_exposure": self.current_exposure,
            "max_exposure": self.max_exposure,
            "intraday_pnl": self.intraday_pnl,
            "max_daily_loss": self.max_daily_loss,
        }
        return RiskEvent(
            reason="Runtime risk kill switch triggered",
            action="CANCEL_ALL_ORDERS",
            metadata=metadata,
        )

    async def dispatch_kill_switch(self) -> RiskEvent:
        """Trigger the kill switch and publish the resulting event asynchronously.

        Returns:
            The `RiskEvent` that was generated.
        """
        event = self.trigger_kill_switch()
        if self.event_bus is not None:
            await self.event_bus.publish(event)
        return event


# ---------------------------------------------------------------------------
# Minimal inline tests (for documentation only)
# ---------------------------------------------------------------------------

"""
Pytest-style examples (conceptual):

def test_daily_loss_breach_triggers_breach_flag() -> None:
    engine = RuntimeRiskEngine(max_daily_loss=1_000.0)
    engine.update_intraday_pnl(-1_500.0)
    assert engine.check_breach() is True


def test_trigger_kill_switch_sets_inactive_and_action() -> None:
    engine = RuntimeRiskEngine()
    event = engine.trigger_kill_switch()
    assert engine.is_active is False
    assert event.action == "CANCEL_ALL_ORDERS"
"""

