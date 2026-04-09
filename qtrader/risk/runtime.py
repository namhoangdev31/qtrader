from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from qtrader.core.events import RiskEvent, RiskPayload
from qtrader.core.types import RiskMetrics

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus
_LOG = logging.getLogger("qtrader.risk.runtime")
__all__ = ["RuntimeRiskEngine"]
try:
    import qtrader_core

    math_engine = qtrader_core.MathEngine()
except ImportError as e:
    _LOG.error("[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked.")
    raise ImportError(
        "qtrader_core is a mandatory dependency for institutional risk management"
    ) from e


@dataclass(slots=True)
class RuntimeRiskEngine:
    max_drawdown: float = 0.1
    max_exposure: float = 1000000.0
    max_daily_loss: float = 5000.0
    max_leverage: float = 5.0
    max_turnover: float = 0.3
    event_bus: EventBus | None = None
    current_drawdown: float = 0.0
    current_exposure: float = 0.0
    current_hwm: float = 0.0
    equity: float = 0.0
    intraday_pnl: float = 0.0
    daily_turnover: float = 0.0
    is_active: bool = True
    current_day: date = field(default_factory=lambda: datetime.now().date())
    portfolio_value: float = 100000.0

    def check_breach(self) -> bool:
        if not self.is_active:
            return False
        if self.current_hwm > 0:
            self.current_drawdown = math_engine.calculate_drawdown(self.equity, self.current_hwm)
            if self.current_drawdown > self.max_drawdown:
                _LOG.critical(
                    "Max drawdown breached: RUST_VAL(%.4f) > LIMIT(%.4f)",
                    self.current_drawdown,
                    self.max_drawdown,
                )
                return True
        if self.current_exposure > self.max_exposure:
            _LOG.warning(
                "Max exposure breached (%.2f > %.2f)", self.current_exposure, self.max_exposure
            )
            return True
        if -self.intraday_pnl > self.max_daily_loss:
            _LOG.critical(
                "Max daily loss breached (%.2f > %.2f)", -self.intraday_pnl, self.max_daily_loss
            )
            return True
        if self.equity > 0:
            leverage = self.current_exposure / self.equity
            if leverage > self.max_leverage:
                _LOG.critical("Max leverage breached (%.2f > %.2f)", leverage, self.max_leverage)
                return True
        if self.daily_turnover > self.max_turnover:
            _LOG.warning(
                "Max daily turnover breached (%.2f > %.2f)", self.daily_turnover, self.max_turnover
            )
            return True
        return False

    def _now(self) -> datetime:
        return datetime.now()

    def update_intraday_pnl(self, pnl_delta: float, now: datetime | None = None) -> None:
        if now is None:
            now = datetime.now()
        today = now.date()
        if today != self.current_day:
            self.current_day = today
            self.intraday_pnl = 0.0
        self.intraday_pnl += pnl_delta

    def trigger_kill_switch(self) -> RiskEvent:
        self.is_active = False
        metadata: dict[str, Any] = {
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "current_exposure": self.current_exposure,
            "max_exposure": self.max_exposure,
            "intraday_pnl": self.intraday_pnl,
            "max_daily_loss": self.max_daily_loss,
        }
        metrics = {
            "current_drawdown": Decimal(str(self.current_drawdown)),
            "max_drawdown": Decimal(str(self.max_drawdown)),
            "current_exposure": Decimal(str(self.current_exposure)),
            "max_exposure": Decimal(str(self.max_exposure)),
            "intraday_pnl": Decimal(str(self.intraday_pnl)),
            "max_daily_loss": Decimal(str(self.max_daily_loss)),
        }
        return RiskEvent(
            source="RuntimeRiskEngine",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="KILL_SWITCH",
                value=Decimal(str(self.current_drawdown)),
                threshold=Decimal(str(self.max_drawdown)),
                metrics=metrics,
                metadata=metadata,
            ),
        )

    async def dispatch_kill_switch(self) -> RiskEvent:
        event = self.trigger_kill_switch()
        if self.event_bus is not None:
            await self.event_bus.publish(event)
        return event

    async def evaluate_risk(self, allocation_weights: Any) -> RiskMetrics:
        return RiskMetrics(
            timestamp=datetime.now(timezone.utc),
            portfolio_var=Decimal("0"),
            portfolio_volatility=Decimal("0"),
            max_drawdown=Decimal("0"),
            leverage=Decimal("0"),
            metadata={},
        )


def create_runtime_risk_engine(
    max_drawdown: float = 0.1,
    max_exposure: float = 1000000.0,
    max_daily_loss: float = 5000.0,
    max_leverage: float = 5.0,
    max_turnover: float = 0.3,
    event_bus: EventBus | None = None,
) -> RuntimeRiskEngine:
    engine = RuntimeRiskEngine()
    engine.max_drawdown = max_drawdown
    engine.max_exposure = max_exposure
    engine.max_daily_loss = max_daily_loss
    engine.max_leverage = max_leverage
    engine.max_turnover = max_turnover
    engine.event_bus = event_bus
    return engine
