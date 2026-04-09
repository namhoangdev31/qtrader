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


try:
    import qtrader_core

    HAS_RUST_CORE = True
    math_engine = qtrader_core.MathEngine()
except ImportError:
    HAS_RUST_CORE = False


class MaxDrawdownLimit:
    """Maximum peak-to-trough drawdown as a fraction of HWM."""

    def __init__(self, pct: float = 0.15) -> None:
        """Initialise the limit.

        Args:
            pct: Maximum allowed drawdown as a fraction of high-water mark (e.g. 0.15 for 15%).
        """
        self._pct = float(pct)
        if not HAS_RUST_CORE:
            raise ImportError("qtrader_core is required for MaxDrawdownLimit")

    def check(self, state: PortfolioState) -> RiskEvent | None:
        """Check whether drawdown exceeds the configured threshold via Rust Core."""
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

        # Even for concentration, we use the pre-calculated HHI from the state
        # which will increasingly be fed from the Rust pipeline.
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
