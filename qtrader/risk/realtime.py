from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl

from qtrader.risk.limits import PortfolioState, RiskLimit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qtrader.core.event_bus import EventBus
    from qtrader.core.events import RiskEvent
    from qtrader.risk.kill_switch import GlobalKillSwitch

__all__ = ["RealTimeRiskEngine"]

_LOG = logging.getLogger("qtrader.risk.realtime")

try:
    import qtrader_core
    from qtrader_core import RiskEngine, WarModeState
    stats_engine = qtrader_core.StatsEngine()
    math_engine = qtrader_core.MathEngine()
except ImportError as e:
    _LOG.error("[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked.")
    raise ImportError("qtrader_core is a mandatory dependency for institutional risk management") from e


@dataclass(slots=True)
class RealTimeRiskEngine:
    """Real-time portfolio risk monitor using high-performance Rust core.

    Tracks positions, PnL history and derived risk measures. Limit checks are
    delegated to the Rust binary engine for sub-100μs performance.
    """

    limits: Sequence[RiskLimit] = field(default_factory=tuple)
    event_bus: EventBus | None = None
    kill_switch: GlobalKillSwitch | None = None
    positions: pl.DataFrame = field(
        default_factory=lambda: pl.DataFrame(
            {
                "symbol": pl.Series([], dtype=pl.String),
                "qty": pl.Series([], dtype=pl.Float64),
                "price": pl.Series([], dtype=pl.Float64),
                "market_value": pl.Series([], dtype=pl.Float64),
                "weight": pl.Series([], dtype=pl.Float64),
            },
        ),
    )
    pnl_history: pl.Series = field(
        default_factory=lambda: pl.Series(name="daily_pnl", values=[], dtype=pl.Float64),
    )
    equity: float = 0.0
    hwm: float = 0.0
    current_drawdown: float = 0.0
    _max_history: int = 252
    _rust_engine: RiskEngine = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the authoritative high-performance Rust core."""
        # Initialize with institutional default limits
        self._rust_engine = RiskEngine(
            max_position_usd=1_000_000.0,
            max_drawdown_pct=0.15,
            max_order_qty=100.0,
            max_order_notional=50_000.0,
            max_orders_per_second=20,
            max_price_deviation_pct=0.03,
            max_leverage=2.0,
            max_hhi=0.5,
            daily_loss_limit=50_000.0,
        )
        _LOG.info("[RISK] Unified RiskCore (Rust) initialized")

    # ------------------------------------------------------------------ #
    # State update methods                                               #
    # ------------------------------------------------------------------ #

    def update_position(self, symbol: str, qty: float, price: float) -> None:
        """Insert or update a single position.

        Args:
            symbol: Instrument identifier.
            qty: Position quantity (signed).
            price: Latest traded or mark price.
        """
        mv = qty * price
        if self.positions.height == 0:
            df = pl.DataFrame(
                {
                    "symbol": [symbol],
                    "qty": [qty],
                    "price": [price],
                    "market_value": [mv],
                },
            )
        else:
            df = self.positions.clone()
            if symbol in df.get_column("symbol").to_list():
                df = df.with_columns(
                    pl.when(pl.col("symbol") == symbol)
                    .then(pl.lit(qty))
                    .otherwise(pl.col("qty"))
                    .alias("qty"),
                    pl.when(pl.col("symbol") == symbol)
                    .then(pl.lit(price))
                    .otherwise(pl.col("price"))
                    .alias("price"),
                )
                df = df.with_columns((pl.col("qty") * pl.col("price")).alias("market_value"))
            else:
                new_row = pl.DataFrame(
                    {
                        "symbol": [symbol],
                        "qty": [qty],
                        "price": [price],
                        "market_value": [mv],
                    },
                )
                # Ensure schema matches by dropping 'weight' if it exists in df
                if "weight" in df.columns:
                    df = df.drop("weight")
                df = pl.concat((df, new_row), how="vertical")

        total_abs_mv = df.get_column("market_value").abs().sum()
        if total_abs_mv > 0.0:
            df = df.with_columns((pl.col("market_value").abs() / total_abs_mv).alias("weight"))
        else:
            df = df.with_columns(pl.lit(0.0).alias("weight"))

        self.positions = df
        self.equity = self.positions.get_column("market_value").sum()
        self.hwm = max(self.hwm, self.equity)
        self.current_drawdown = self._compute_drawdown()

    def update_pnl(self, pnl_delta: float) -> None:
        """Append a new daily PnL observation and maintain rolling history.

        Args:
            pnl_delta: Realised or marked-to-market PnL for the day.
        """
        if self.pnl_history.len() == 0:
            series = pl.Series(name="daily_pnl", values=[pnl_delta], dtype=pl.Float64)
        else:
            series = pl.concat(
                [self.pnl_history, pl.Series(name="daily_pnl", values=[pnl_delta])],
                how="vertical",
            )
        if series.len() > self._max_history:
            series = series.tail(self._max_history)
        self.pnl_history = series

    # ------------------------------------------------------------------ #
    # Risk metrics                                                       #
    # ------------------------------------------------------------------ #

    def compute_var(self, confidence: float = 0.95, horizon_days: int = 1) -> float:
        """Compute historical-simulation VaR using authoritative Rust acceleration."""
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0

        returns = (self.pnl_history / self.equity).to_list()
        alpha = 1.0 - confidence
        var_ret = stats_engine.calculate_historical_es(returns, alpha)
        return abs(float(var_ret * self.equity * (horizon_days**0.5)))

    def compute_cvar(self, confidence: float = 0.95) -> float:
        """Compute Expected Shortfall using authoritative Rust StatsEngine."""
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0

        returns = (self.pnl_history / self.equity).to_list()
        alpha = 1.0 - confidence
        es_ret = stats_engine.calculate_historical_es(returns, alpha)
        return abs(float(es_ret * self.equity))

    def compute_ruin_probability(self) -> float:
        """Estimate probability of ruin based on recent performance streaks."""
        if self.pnl_history.len() < 10:
            return 0.0
            
        wins = self.pnl_history.filter(self.pnl_history > 0).len()
        losses = self.pnl_history.filter(self.pnl_history < 0).len()
        total = wins + losses
        
        if total == 0: return 0.0
        
        win_rate = wins / total
        avg_win = self.pnl_history.filter(self.pnl_history > 0).mean() or 0.0
        avg_loss = abs(self.pnl_history.filter(self.pnl_history < 0).mean() or 1.0)
        edge = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss
        
        if edge <= 0: return 1.0
        
        # Simple analytical edge-based Ruin formula
        # P(Ruin) = ((1-edge)/(1+edge))^units_left
        units_left = self.equity / avg_loss if avg_loss > 0 else 100.0
        return ((1.0 - edge) / (1.0 + edge)) ** units_left

    def compute_hhi(self) -> float:
        """Compute Herfindahl-Hirschman Index of position concentration."""
        if self.positions.height == 0:
            return 0.0
        weights = self.positions.get_column("weight")
        hhi_value = float((weights**2).sum())
        return hhi_value

    # ------------------------------------------------------------------ #
    # Limits & EventBus integration                                     #
    # ------------------------------------------------------------------ #

    def _build_portfolio_state(self) -> PortfolioState:
        """Construct a `PortfolioState` from the current engine state."""
        daily_pnl = self.pnl_history.tail(1).item() if self.pnl_history.len() > 0 else 0.0
        var_95 = self.compute_var(confidence=0.95, horizon_days=1)
        hhi = self.compute_hhi()
        return PortfolioState(
            equity=self.equity,
            hwm=self.hwm,
            positions=self.positions,
            daily_pnl=daily_pnl,
            var_95=var_95,
            hhi=hhi,
        )

    def check_all_limits(self) -> list[RiskEvent]:
        """Evaluate authoritative Rust limits and optional research plugins.

        Returns:
            List of `RiskEvent` objects; empty list means all limits are satisfied.
        """
        breaches: list[RiskEvent] = []
        
        # 1. Mandatory high-performance Rust Core checks
        try:
            gross_exposure = self.positions.get_column("market_value").abs().sum()
            self._rust_engine.check_portfolio_state(
                current_equity=self.equity,
                peak_equity=self.hwm,
                gross_exposure=gross_exposure,
            )
        except ValueError as e:
            # Map Rust authoritative error to RiskEvent
            reason = str(e)
            risk_type = "PORTFOLIO"
            if "DRAWDOWN" in reason.upper(): risk_type = "DRAWDOWN"
            if "LEVERAGE" in reason.upper(): risk_type = "EXPOSURE"
            
            breaches.append(RiskEvent(
                reason=reason,
                action="BLOCK_TRADING",
                metadata={
                    "risk_type": risk_type,
                    "source": "RUST_CORE",
                    "equity": self.equity,
                    "hwm": self.hwm,
                }
            ))

        # 2. Sequential Custom Limits (Research-only plugins)
        if self.limits:
            state = self._build_portfolio_state()
            for limit in self.limits:
                event = limit.check(state)
                if event is not None:
                    breaches.append(event)
        
        return breaches

    async def publish_breaches(self) -> list[RiskEvent]:
        """Publish breaches and trigger authoritative hardware-near safety actions."""
        breaches = self.check_all_limits()
        if not breaches:
            return breaches

        # Identify critical breaches requiring immediate halt
        critical_breach = any(
            event.metadata.get("risk_type") in ("DRAWDOWN", "VAR", "EXPOSURE") or
            getattr(event, "payload", None) and getattr(event.payload, "risk_type", None) in ("DRAWDOWN", "VAR", "EXPOSURE")
            for event in breaches
        )

        if self.event_bus:
            for event in breaches:
                await self.event_bus.publish(event)
        
        if critical_breach and self.kill_switch:
            self.kill_switch.trigger_on_critical_failure(
                "RISK_LIMIT_BREACH",
                f"Critical risk breach detected (State: {self._rust_engine.get_state()})",
            )
            
        return breaches

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _compute_drawdown(self) -> float:
        """Compute current drawdown as a fraction of HWM."""
        if self.hwm <= 0.0:
            return 0.0
        return (self.hwm - self.equity) / self.hwm


# ---------------------------------------------------------------------------
# Minimal inline tests (for documentation only)
# ---------------------------------------------------------------------------

"""
Pytest-style examples (conceptual):

def test_compute_hhi_single_position() -> None:
    engine = RealTimeRiskEngine()
    engine.update_position("AAPL", qty=100.0, price=150.0)
    hhi = engine.compute_hhi()
    assert hhi == pytest.approx(1.0)


def test_var_and_cvar_non_negative() -> None:
    engine = RealTimeRiskEngine()
    for pnl in (-100.0, 50.0, -20.0, 10.0):
        engine.update_pnl(pnl)
    var_95 = engine.compute_var()
    cvar_95 = engine.compute_cvar()
    assert var_95 >= 0.0
    assert cvar_95 >= 0.0


async def test_publish_breaches_uses_event_bus(event_bus: EventBus) -> None:
    engine = RealTimeRiskEngine(limits=[], event_bus=event_bus)
    events = await engine.publish_breaches()
    assert events == []
"""
