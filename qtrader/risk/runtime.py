from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from qtrader.core.events import RiskEvent
from qtrader.core.types import RiskMetrics

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus

__all__ = ["RuntimeRiskEngine"]

try:
    import qtrader_core
    math_engine = qtrader_core.MathEngine()
except ImportError as e:
    _LOG.error("[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked.")
    raise ImportError("qtrader_core is a mandatory dependency for institutional risk management") from e


@dataclass(slots=True)
class RuntimeRiskEngine:
    """Real-time monitoring and safety guardrails.

    This component is intentionally lightweight and focused on process-level
    kill-switch behaviour. It is complementary to the portfolio-level
    `RealTimeRiskEngine`.
    """

    # Risk limits
    max_drawdown: float = 0.1
    max_exposure: float = 1_000_000.0
    max_daily_loss: float = 5_000.0
    max_leverage: float = 5.0  # 5x leverage cap
    max_turnover: float = 0.3  # 30% daily turnover constraint
    
    event_bus: EventBus | None = None

    # State tracking
    current_drawdown: float = 0.0
    current_exposure: float = 0.0
    current_hwm: float = 0.0
    equity: float = 0.0
    intraday_pnl: float = 0.0
    daily_turnover: float = 0.0
    is_active: bool = True
    current_day: date = field(
        default_factory=lambda: datetime.now().date(),
    )
    
    # Portfolio value for leverage calculation
    portfolio_value: float = 100000.0

    def check_breach(self) -> bool:
        """Check whether any safety limits have been breached via authoritative Rust checks.

        Returns:
            ``True`` if a breach is detected, otherwise ``False``.
        """
        if not self.is_active:
            return False

        # 1. Check max drawdown using Rust precision
        if self.current_hwm > 0:
            self.current_drawdown = math_engine.calculate_drawdown(self.equity, self.current_hwm)
            if self.current_drawdown > self.max_drawdown:
                _LOG.critical(
                    "Max drawdown breached: RUST_VAL(%.4f) > LIMIT(%.4f)", 
                    self.current_drawdown, 
                    self.max_drawdown
                )
                return True

        # 2. Check max exposure
        if self.current_exposure > self.max_exposure:
            _LOG.warning("Max exposure breached (%.2f > %.2f)", self.current_exposure, self.max_exposure)
            return True

        # 3. Check max daily loss
        if -self.intraday_pnl > self.max_daily_loss:
            _LOG.critical(
                "Max daily loss breached (%.2f > %.2f)",
                -self.intraday_pnl,
                self.max_daily_loss,
            )
            return True

        # 4. Check max leverage
        if self.equity > 0:
            leverage = self.current_exposure / self.equity
            if leverage > self.max_leverage:
                _LOG.critical(
                    "Max leverage breached (%.2f > %.2f)",
                    leverage,
                    self.max_leverage,
                )
                return True

        # 5. Check max turnover
        if self.daily_turnover > self.max_turnover:
            _LOG.warning(
                "Max daily turnover breached (%.2f > %.2f)",
                self.daily_turnover,
                self.max_turnover,
            )
            return True

        return False
        
    def _now(self) -> datetime:
        return datetime.now()

    def update_intraday_pnl(self, pnl_delta: float, now: datetime | None = None) -> None:
        """Update intraday PnL, resetting at UTC midnight boundaries.

        Args:
            pnl_delta: Incremental PnL to add to the current day.
            now: Optional timestamp; defaults to current UTC time.
        """
        if now is None:
            now = datetime.now()
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
            symbol="PORTFOLIO",
            metrics={
                "current_drawdown": self.current_drawdown,
                "max_drawdown": self.max_drawdown,
                "current_exposure": self.current_exposure,
                "max_exposure": self.max_exposure,
                "intraday_pnl": self.intraday_pnl,
                "max_daily_loss": self.max_daily_loss,
            },
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

    async def evaluate_risk(self, allocation_weights: Any) -> RiskMetrics:
        """Evaluate risk for a given allocation.

        This is a simplified risk evaluation for demonstration purposes.
        In a production system, this would involve more complex calculations
        based on current market data, positions, and the proposed allocation.

        Args:
            allocation_weights: The proposed allocation weights.

        Returns:
            RiskMetrics: The calculated risk metrics.
        """
        # For now, we return zero risk metrics as a placeholder.
        # A real implementation would calculate VaR, volatility, drawdown, and leverage
        # based on the allocation and current market conditions.
        return RiskMetrics(
            timestamp=datetime.utcnow(),
            portfolio_var=Decimal('0'),
            portfolio_volatility=Decimal('0'),
            max_drawdown=Decimal('0'),
            leverage=Decimal('0'),
            metadata={}
        )


def create_runtime_risk_engine(
    max_drawdown: float = 0.1,
    max_exposure: float = 1_000_000.0,
    max_daily_loss: float = 5_000.0,
    max_leverage: float = 5.0,
    max_turnover: float = 0.3,
    event_bus: EventBus | None = None,
) -> RuntimeRiskEngine:
    """Factory function to create a RuntimeRiskEngine with custom limits.
    
    Args:
        max_drawdown: Maximum allowed drawdown (default 0.1 = 10%)
        max_exposure: Maximum allowed exposure in currency units (default 1,000,000)
        max_daily_loss: Maximum allowed daily loss in currency units (default 5,000)
        max_leverage: Maximum allowed leverage ratio (default 5.0 = 5x)
        max_turnover: Maximum allowed daily turnover ratio (default 0.3 = 30%)
        event_bus: Optional event bus for publishing risk events
        
    Returns:
        Configured RuntimeRiskEngine instance
    """
    engine = RuntimeRiskEngine()
    engine.max_drawdown = max_drawdown
    engine.max_exposure = max_exposure
    engine.max_daily_loss = max_daily_loss
    engine.max_leverage = max_leverage
    engine.max_turnover = max_turnover
    engine.event_bus = event_bus
    return engine


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