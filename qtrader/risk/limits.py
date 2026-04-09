from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from qtrader.core.events import RiskEvent, RiskPayload

if TYPE_CHECKING:
    import polars as pl
__all__ = [
    "DailyLossLimit",
    "GrossExposureLimit",
    "MaxConcentrationLimit",
    "MaxDrawdownLimit",
    "PortfolioState",
    "RiskLimit",
    "VaRBreachLimit",
]


@dataclass(slots=True)
class PortfolioState:
    equity: float
    hwm: float
    positions: pl.DataFrame
    daily_pnl: float
    var_95: float
    hhi: float


class RiskLimit(Protocol):
    def check(self, state: PortfolioState) -> RiskEvent | None:
        pass


try:
    import qtrader_core

    HAS_RUST_CORE = True
    math_engine = qtrader_core.MathEngine()
except ImportError:
    HAS_RUST_CORE = False


class MaxDrawdownLimit:
    def __init__(self, pct: float = 0.15) -> None:
        self._pct = float(pct)
        if not HAS_RUST_CORE:
            raise ImportError("qtrader_core is required for MaxDrawdownLimit")

    def check(self, state: PortfolioState) -> RiskEvent | None:
        if state.hwm <= 0.0:
            return None
        drawdown = math_engine.calculate_drawdown(state.equity, state.hwm)
        if drawdown <= self._pct:
            return None
        return RiskEvent(
            source="MaxDrawdownLimit",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="MAX_DRAWDOWN",
                value=Decimal(str(drawdown)),
                threshold=Decimal(str(self._pct)),
                metadata={
                    "reason": f"Max drawdown limit breached: {drawdown:.2%} > {self._pct:.2%}",
                    "equity": state.equity,
                    "hwm": state.hwm,
                    "source": "RUST_CORE",
                },
            ),
        )


class DailyLossLimit:
    def __init__(self, usd: float = 5000.0) -> None:
        self._usd = float(usd)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        if state.daily_pnl >= 0.0:
            return None
        loss = -state.daily_pnl
        if loss <= self._usd:
            return None
        return RiskEvent(
            source="DailyLossLimit",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="DAILY_LOSS",
                value=Decimal(str(loss)),
                threshold=Decimal(str(self._usd)),
                metadata={
                    "reason": f"Daily loss limit breached: ${loss:,.2f} > ${self._usd:,.2f}",
                    "equity": state.equity,
                    "source": "RUST_CORE",
                },
            ),
        )


class MaxConcentrationLimit:
    def __init__(self, max_weight: float = 0.2) -> None:
        self._max_weight = float(max_weight)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        if state.positions.height == 0:
            return None
        max_weight_value = state.positions.get_column("weight").abs().max()
        if max_weight_value <= self._max_weight and state.hhi <= self._max_weight:
            return None
        return RiskEvent(
            source="MaxConcentrationLimit",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="CONCENTRATION",
                value=Decimal(str(max_weight_value)),
                threshold=Decimal(str(self._max_weight)),
                metadata={
                    "reason": "Concentration limit breached",
                    "hhi": state.hhi,
                    "source": "RUST_CORE",
                },
            ),
        )


class GrossExposureLimit:
    def __init__(self, max_leverage: float = 2.0) -> None:
        self._max_leverage = float(max_leverage)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        if state.equity <= 0.0 or state.positions.height == 0:
            return None
        gross_exposure = state.positions.get_column("market_value").abs().sum()
        leverage = gross_exposure / state.equity
        if leverage <= self._max_leverage:
            return None
        return RiskEvent(
            source="GrossExposureLimit",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="GROSS_EXPOSURE",
                value=Decimal(str(leverage)),
                threshold=Decimal(str(self._max_leverage)),
                metadata={
                    "reason": f"Gross exposure limit breached: {leverage:.2f}x > {self._max_leverage:.2f}x",
                    "gross_exposure": gross_exposure,
                    "equity": state.equity,
                    "source": "RUST_CORE",
                },
            ),
        )


class VaRBreachLimit:
    def __init__(self, var_threshold_pct: float = 0.02) -> None:
        self._var_threshold_pct = float(var_threshold_pct)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        if state.equity <= 0.0 or state.var_95 <= 0.0:
            return None
        var_fraction = state.var_95 / state.equity
        if var_fraction <= self._var_threshold_pct:
            return None
        metadata: dict[str, Any] = {
            "limit": "VAR_BREACH",
            "threshold_pct": self._var_threshold_pct,
            "var_95": state.var_95,
            "var_fraction": var_fraction,
            "equity": state.equity,
        }
        return RiskEvent(
            source="VaRBreachLimit",
            payload=RiskPayload(
                symbol="PORTFOLIO",
                risk_type="VAR_BREACH",
                value=Decimal(str(var_fraction)),
                threshold=Decimal(str(self._var_threshold_pct)),
                metadata={
                    "reason": "VaR limit breached",
                    "var_95": state.var_95,
                    "equity": state.equity,
                    "source": "RESEARCH_MODULE",
                },
            ),
        )
