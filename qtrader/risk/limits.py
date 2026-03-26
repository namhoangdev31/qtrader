from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from qtrader.core.event import RiskEvent

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
    """Immutable snapshot of the current portfolio state.

    Attributes:
        equity: Current portfolio equity in base currency.
        hwm: High-water mark equity in base currency.
        positions: Positions DataFrame with columns:
            - symbol: str
            - weight: float
            - market_value: float
        daily_pnl: Realised or marked-to-market PnL for the current day.
        var_95: One-day 95% Value-at-Risk in absolute currency units.
        hhi: Herfindahl-Hirschman Index of position concentration.
    """

    equity: float
    hwm: float
    positions: pl.DataFrame
    daily_pnl: float
    var_95: float
    hhi: float


class RiskLimit(Protocol):
    """Protocol for portfolio-level risk limits."""

    def check(self, state: PortfolioState) -> RiskEvent | None:  # pragma: no cover - interface
        """Evaluate the limit against the given state.

        Args:
            state: Snapshot of the current portfolio state.

        Returns:
            A `RiskEvent` describing the breach, or ``None`` if the limit is not breached.
        """


class MaxDrawdownLimit:
    """Maximum peak-to-trough drawdown as a fraction of HWM."""

    def __init__(self, pct: float = 0.15) -> None:
        """Initialise the limit.

        Args:
            pct: Maximum allowed drawdown as a fraction of high-water mark (e.g. 0.15 for 15%).
        """
        self._pct = float(pct)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether drawdown exceeds the configured threshold."""
        if state.hwm <= 0.0:
            return None
        drawdown = (state.hwm - state.equity) / state.hwm
        if drawdown <= self._pct:
            return None
        metadata: dict[str, Any] = {
            "limit": "MAX_DRAWDOWN",
            "threshold_pct": self._pct,
            "drawdown_pct": drawdown,
            "equity": state.equity,
            "hwm": state.hwm,
        }
        return RiskEvent(
            reason="Max drawdown limit breached",
            action="BLOCK_TRADING",
            metadata=metadata,
        )


class DailyLossLimit:
    """Maximum absolute daily loss in base currency."""

    def __init__(self, usd: float = 5000.0) -> None:
        """Initialise the limit.

        Args:
            usd: Maximum allowed loss for the current day in base currency.
        """
        self._usd = float(usd)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether daily loss exceeds the configured threshold."""
        if state.daily_pnl >= 0.0:
            return None
        loss = -state.daily_pnl
        if loss <= self._usd:
            return None
        metadata: dict[str, Any] = {
            "limit": "DAILY_LOSS",
            "threshold_usd": self._usd,
            "loss_usd": loss,
            "equity": state.equity,
        }
        return RiskEvent(
            reason="Daily loss limit breached",
            action="BLOCK_TRADING",
            metadata=metadata,
        )


class MaxConcentrationLimit:
    """Maximum concentration based on Herfindahl-Hirschman Index or max weight."""

    def __init__(self, max_weight: float = 0.20) -> None:
        """Initialise the limit.

        Args:
            max_weight: Maximum allowed single-position portfolio weight (e.g. 0.20 for 20%).
        """
        self._max_weight = float(max_weight)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether concentration exceeds the configured threshold."""
        if state.positions.height == 0:
            return None

        max_weight_expr = state.positions.get_column("weight").abs().max()
        max_weight_value = float(max_weight_expr) if max_weight_expr is not None else 0.0

        if max_weight_value <= self._max_weight and state.hhi <= self._max_weight:
            return None

        metadata: dict[str, Any] = {
            "limit": "CONCENTRATION",
            "threshold_weight": self._max_weight,
            "max_weight": max_weight_value,
            "hhi": state.hhi,
        }
        return RiskEvent(
            reason="Concentration limit breached",
            action="REDUCE_POSITIONS",
            metadata=metadata,
        )


class GrossExposureLimit:
    """Maximum portfolio gross exposure measured as leverage."""

    def __init__(self, max_leverage: float = 2.0) -> None:
        """Initialise the limit.

        Args:
            max_leverage: Maximum allowed gross exposure / equity leverage.
        """
        self._max_leverage = float(max_leverage)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether gross exposure exceeds the configured leverage threshold."""
        if state.equity <= 0.0 or state.positions.height == 0:
            return None

        gross_exposure_series = state.positions.get_column("market_value").abs().sum()
        gross_exposure = float(gross_exposure_series)
        leverage = gross_exposure / state.equity

        if leverage <= self._max_leverage:
            return None

        metadata: dict[str, Any] = {
            "limit": "GROSS_EXPOSURE",
            "threshold_leverage": self._max_leverage,
            "gross_exposure": gross_exposure,
            "leverage": leverage,
            "equity": state.equity,
        }
        return RiskEvent(
            reason="Gross exposure limit breached",
            action="REDUCE_LEVERAGE",
            metadata=metadata,
        )


class VaRBreachLimit:
    """Portfolio Value-at-Risk as percentage of equity."""

    def __init__(self, var_threshold_pct: float = 0.02) -> None:
        """Initialise the limit.

        Args:
            var_threshold_pct: Maximum allowed one-day VaR as a fraction of equity.
        """
        self._var_threshold_pct = float(var_threshold_pct)

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether VaR exceeds the configured threshold."""
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
            reason="VaR limit breached",
            action="BLOCK_TRADING",
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Minimal inline tests (for documentation only)
# ---------------------------------------------------------------------------

"""
Pytest-style examples (conceptual):

def test_max_drawdown_limit_triggers() -> None:
    positions = pl.DataFrame(
        {"symbol": ["AAPL"], "weight": [1.0], "market_value": [100_000.0]},
    )
    state = PortfolioState(
        equity=80_000.0,
        hwm=100_000.0,
        positions=positions,
        daily_pnl=-1_000.0,
        var_95=2_000.0,
        hhi=1.0,
    )
    limit = MaxDrawdownLimit(pct=0.15)
    event = limit.check(state)
    assert event is not None
    assert event.action == "BLOCK_TRADING"


def test_gross_exposure_limit_triggers() -> None:
    positions = pl.DataFrame(
        {
            "symbol": ["AAPL", "MSFT"],
            "weight": [0.5, 0.5],
            "market_value": [150_000.0, 150_000.0],
        },
    )
    state = PortfolioState(
        equity=100_000.0,
        hwm=120_000.0,
        positions=positions,
        daily_pnl=0.0,
        var_95=3_000.0,
        hhi=0.5,
    )
    limit = GrossExposureLimit(max_leverage=2.0)
    event = limit.check(state)
    assert event is not None
    assert event.action == "REDUCE_LEVERAGE"


def test_var_breach_limit_triggers() -> None:
    positions = pl.DataFrame(
        {"symbol": ["AAPL"], "weight": [1.0], "market_value": [100_000.0]},
    )
    state = PortfolioState(
        equity=100_000.0,
        hwm=100_000.0,
        positions=positions,
        daily_pnl=0.0,
        var_95=5_000.0,
        hhi=1.0,
    )
    limit = VaRBreachLimit(var_threshold_pct=0.02)
    event = limit.check(state)
    assert event is not None
    assert event.action == "BLOCK_TRADING"
"""
