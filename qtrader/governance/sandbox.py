from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

import numpy as np
import polars as pl

from qtrader.core.events import (
    SandboxErrorEvent,
    SandboxErrorPayload,
    SandboxReportEvent,
    SandboxReportPayload,
)
from qtrader.core.logger import log as logger
from qtrader.governance.simulator_adapter import SimulatorAdapter

if TYPE_CHECKING:
    from qtrader.core.event_bus import EventBus


class Strategy(Protocol):
    strategy_id: str

    def on_candle(self, df_candle: pl.DataFrame) -> None: ...

    def get_signal(self) -> dict[str, Any]: ...


class StrategySandbox:
    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def run_simulation(
        self, strategy: Strategy, market_data: pl.DataFrame
    ) -> SandboxReportEvent | None:
        strategy_id = "UNKNOWN"
        try:
            if not strategy or market_data is None:
                raise ValueError("Strategy or Market Data is NULL")
            strategy_id = strategy.strategy_id
            adapter = SimulatorAdapter()
            for candle in market_data.to_dicts():
                df_curr = pl.DataFrame([candle])
                strategy.on_candle(df_curr)
                signal = strategy.get_signal()
                if signal and signal.get("action") in ["BUY", "SELL"]:
                    adapter.process_signal(
                        timestamp=int(candle["timestamp"]),
                        symbol=str(candle.get("symbol", "UNKNOWN")),
                        side=str(signal["action"]),
                        price=float(candle["close"]),
                        quantity=float(signal.get("quantity", 0.0)),
                    )
            report = await self._analyze_results(strategy_id, adapter)
            await self._event_bus.publish(report)
            logger.info(f"SANDBOX_SIM_COMPLETE | {strategy_id}")
            return report
        except Exception as e:
            logger.error(f"SANDBOX_SIM_FAILURE | {strategy_id} | {e!s}")
            await self._emit_error(strategy_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _analyze_results(
        self, strategy_id: str, adapter: SimulatorAdapter
    ) -> SandboxReportEvent:
        trades = adapter.trades
        if not trades:
            return SandboxReportEvent(
                trace_id=self._system_trace,
                source="StrategySandbox",
                payload=SandboxReportPayload(
                    strategy_id=strategy_id,
                    pnl=0.0,
                    drawdown=0.0,
                    sharpe=0.0,
                    status="EMPTY",
                    trade_count=0,
                ),
            )
        pnl = sum([t.price * t.quantity * (1 if t.side == "SELL" else -1) for t in trades])
        raw_eq = [t.price * t.quantity * (1 if t.side == "SELL" else -1) for t in trades]
        equity_series = np.cumsum(raw_eq)
        denom = equity_series[:-1] + 1e-09
        returns = np.diff(equity_series) / denom if len(equity_series) > 1 else np.array([0.0])
        sharpe_raw = np.mean(returns) / (np.std(returns) + 1e-09)
        sharpe = float(sharpe_raw * math.sqrt(252)) if len(returns) > 1 else 0.0
        peak = -np.inf
        drawdown = 0.0
        curr_equity = 0.0
        for val in equity_series:
            curr_equity += val
            peak = max(peak, curr_equity)
            dd = peak - curr_equity
            drawdown = max(drawdown, dd)
        return SandboxReportEvent(
            trace_id=self._system_trace,
            source="StrategySandbox",
            payload=SandboxReportPayload(
                strategy_id=strategy_id,
                pnl=float(pnl),
                drawdown=float(drawdown),
                sharpe=float(sharpe),
                status="SUCCESS",
                trade_count=len(trades),
            ),
        )

    async def _emit_error(self, strategy_id: str, err_type: str, details: str) -> None:
        error_event = SandboxErrorEvent(
            trace_id=self._system_trace,
            source="StrategySandbox",
            payload=SandboxErrorPayload(
                strategy_id=strategy_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
