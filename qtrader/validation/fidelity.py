from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast
from uuid import UUID

import numpy as np

from qtrader.core.events import (
    FidelityErrorEvent,
    FidelityErrorPayload,
    FidelityReportEvent,
    FidelityReportPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    import polars as pl

    from qtrader.core.event_bus import EventBus


class FidelityEngine:
    """
    Backtest Fidelity and Simulation Reality Engine.

    Measures the divergence between theoretical backtest results and
    real-world execution (live or replay) to prevent overfitting:
    - PnL Divergence Appraisal
    - Slippage Fidelity Validation
    - Price Alignment Error
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the fidelity appraisal engine.
        """
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def compute_fidelity(
        self, strategy_id: str, backtest_trades: pl.DataFrame, live_trades: pl.DataFrame
    ) -> FidelityReportEvent | None:
        """
        Compute industrial-grade fidelity metrics between backtest and live data.
        """
        try:
            if backtest_trades.is_empty() or live_trades.is_empty():
                raise ValueError("Incomplete dataset: Backtest or Live trades are empty.")

            # 1. Alignment Logic: Join by closest timestamp
            aligned = backtest_trades.join_asof(
                live_trades,
                on="timestamp",
                by="symbol",
                strategy="nearest",
                suffix="_live",
            )

            if aligned.is_empty():
                raise ValueError("Zero trade alignment reached during fidelity join.")

            # 2. Metric Computation: Divergence vectors
            # Using cast('float', ...) to satisfy ruff TC006 and mypy strictness
            pnl_diff = cast("float", (aligned["pnl"] - aligned["pnl_live"]).abs().mean() or 0.0)
            slippage_diff = cast(
                "float", (aligned["slippage"] - aligned["slippage_live"]).abs().mean() or 0.0
            )
            price_diff = cast(
                "float", (aligned["price"] - aligned["price_live"]).abs().mean() or 0.0
            )

            # 3. Fidelity Score: F = 1 - (E / scale)
            bt_avg_pnl = cast("float", aligned["pnl"].abs().mean() or 0.0)
            scale = max(bt_avg_pnl, 1.0)  # avoid division by zero
            fidelity_score = 1.0 - (pnl_diff / scale)

            # Clamp fidelity score to [0, 1]
            fidelity_score = float(np.clip(fidelity_score, 0.0, 1.0))

            # 4. Report Broadcast
            report_event = FidelityReportEvent(
                trace_id=self._system_trace,
                source="FidelityEngine",
                payload=FidelityReportPayload(
                    strategy_id=strategy_id,
                    pnl_diff=pnl_diff,
                    slippage_diff=slippage_diff,
                    price_diff=price_diff,
                    fidelity_score=fidelity_score,
                    trade_count=aligned.height,
                    metadata={"timestamp_ms": int(time.time() * 1000)},
                ),
            )

            await self._event_bus.publish(report_event)
            logger.info(f"FIDELITY_COMPLETE | {strategy_id} | Score: {fidelity_score:.4f}")

            return report_event

        except Exception as e:
            logger.error(f"FIDELITY_PIPELINE_FAILURE | {strategy_id} | {e!s}")
            await self._emit_error(strategy_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, strategy_id: str, err_type: str, details: str) -> None:
        """Emit a FidelityErrorEvent to the global bus."""
        error_event = FidelityErrorEvent(
            trace_id=self._system_trace,
            source="FidelityEngine",
            payload=FidelityErrorPayload(
                strategy_id=strategy_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
