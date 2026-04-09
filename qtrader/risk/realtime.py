from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

import polars as pl

from qtrader.risk.limits import PortfolioState, RiskLimit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from qtrader.core.event_bus import EventBus
    from qtrader.risk.kill_switch import GlobalKillSwitch

from qtrader.core.events import RiskEvent, RiskPayload

__all__ = ["RealTimeRiskEngine"]
_LOG = logging.getLogger("qtrader.risk.realtime")

try:
    import qtrader_core
    from qtrader_core import RiskEngine

    stats_engine = qtrader_core.StatsEngine()
    math_engine = qtrader_core.MathEngine()
except ImportError as e:
    _LOG.error("[RISK] Institutional Risk Core (qtrader_core) is missing. System startup blocked.")
    raise ImportError(
        "qtrader_core is a mandatory dependency for institutional risk management"
    ) from e


@dataclass(slots=True)
class RealTimeRiskEngine:
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
            }
        )
    )
    pnl_history: pl.Series = field(
        default_factory=lambda: pl.Series(name="daily_pnl", values=[], dtype=pl.Float64)
    )
    equity: float = 0.0
    hwm: float = 0.0
    current_drawdown: float = 0.0
    _max_history: int = 252
    _rust_engine: RiskEngine = field(init=False)

    def __post_init__(self) -> None:
        self._rust_engine = RiskEngine(
            max_position_usd=1000000.0,
            max_drawdown_pct=0.15,
            max_order_qty=100.0,
            max_order_notional=50000.0,
            max_orders_per_second=20,
            max_price_deviation_pct=0.03,
            max_leverage=2.0,
            max_hhi=0.5,
            daily_loss_limit=50000.0,
        )
        _LOG.info("[RISK] Unified RiskCore (Rust) initialized")

    def update_position(self, symbol: str, qty: float, price: float) -> None:
        mv = qty * price
        if self.positions.height == 0:
            df = pl.DataFrame(
                {"symbol": [symbol], "qty": [qty], "price": [price], "market_value": [mv]}
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
                    {"symbol": [symbol], "qty": [qty], "price": [price], "market_value": [mv]}
                )
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
        if self.pnl_history.len() == 0:
            series = pl.Series(name="daily_pnl", values=[pnl_delta], dtype=pl.Float64)
        else:
            series = pl.concat(
                [self.pnl_history, pl.Series(name="daily_pnl", values=[pnl_delta])], how="vertical"
            )
        if series.len() > self._max_history:
            series = series.tail(self._max_history)
        self.pnl_history = series

    def compute_var(self, confidence: float = 0.95, horizon_days: int = 1) -> float:
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0
        returns = (self.pnl_history / self.equity).to_list()
        alpha = 1.0 - confidence
        var_ret = stats_engine.calculate_historical_es(returns, alpha)
        return abs(float(var_ret * self.equity * horizon_days**0.5))

    def compute_cvar(self, confidence: float = 0.95) -> float:
        if self.pnl_history.len() == 0 or self.equity <= 0.0:
            return 0.0
        returns = (self.pnl_history / self.equity).to_list()
        alpha = 1.0 - confidence
        es_ret = stats_engine.calculate_historical_es(returns, alpha)
        return abs(float(es_ret * self.equity))

    def compute_ruin_probability(self) -> float:
        min_pnl_history = 10
        if self.pnl_history.len() < min_pnl_history:
            return 0.0
        wins = self.pnl_history.filter(self.pnl_history > 0).len()
        losses = self.pnl_history.filter(self.pnl_history < 0).len()
        total = wins + losses
        if total == 0:
            return 0.0
        win_rate = wins / total
        avg_win = self.pnl_history.filter(self.pnl_history > 0).mean() or 0.0
        avg_loss = abs(self.pnl_history.filter(self.pnl_history < 0).mean() or 1.0)
        edge = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_loss
        if edge <= 0:
            return 1.0
        units_left = self.equity / avg_loss if avg_loss > 0 else 100.0
        return ((1.0 - edge) / (1.0 + edge)) ** units_left

    def compute_hhi(self) -> float:
        if self.positions.height == 0:
            return 0.0
        weights = self.positions.get_column("weight")
        hhi_value = float((weights**2).sum())
        return hhi_value

    def _build_portfolio_state(self) -> PortfolioState:
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
        breaches: list[RiskEvent] = []
        try:
            gross_exposure = self.positions.get_column("market_value").abs().sum()
            self._rust_engine.check_portfolio_state(
                current_equity=self.equity, peak_equity=self.hwm, gross_exposure=gross_exposure
            )
        except ValueError as e:
            reason = str(e)
            risk_type = "PORTFOLIO"
            if "DRAWDOWN" in reason.upper():
                risk_type = "DRAWDOWN"
            if "LEVERAGE" in reason.upper():
                risk_type = "EXPOSURE"

            breaches.append(
                RiskEvent(
                    source="RealTimeRiskEngine",
                    payload=RiskPayload(
                        symbol="PORTFOLIO",
                        risk_type=risk_type,
                        value=Decimal(str(self.equity)),
                        threshold=Decimal("0.0"),
                        metadata={
                            "reason": reason,
                            "source": "RUST_CORE",
                            "equity": self.equity,
                            "hwm": self.hwm,
                        },
                    ),
                )
            )
        if self.limits:
            state = self._build_portfolio_state()
            for limit in self.limits:
                event = limit.check(state)
                if event is not None:
                    breaches.append(event)
        return breaches

    async def publish_breaches(self) -> list[RiskEvent]:
        breaches = self.check_all_limits()
        if not breaches:
            return breaches
        critical_breach = any(
            event.metadata.get("risk_type") in ("DRAWDOWN", "VAR", "EXPOSURE")
            or (
                getattr(event, "payload", None)
                and getattr(event.payload, "risk_type", None) in ("DRAWDOWN", "VAR", "EXPOSURE")
            )
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

    def _compute_drawdown(self) -> float:
        if self.hwm <= 0.0:
            return 0.0
        return (self.hwm - self.equity) / self.hwm
