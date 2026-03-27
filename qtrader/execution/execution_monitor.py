from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.execution.execution_monitor")


class LiveExecutionMonitor:
    """
    Principal Execution Monitoring System.

    Objective: Continuously track execution quality indices ($Slippage, Fill Rate, Latency$)
    under live trading conditions to detect operational degradation.

    Model: Transaction Cost Analysis (TCA) Forensics.
    """

    def __init__(self) -> None:
        """
        Initialize the institutional execution monitor.
        """
        # Per-strategy metrological indexing.
        self._strategy_slippage_trace: dict[str, list[float]] = {}
        self._strategy_latency_trace: dict[str, list[float]] = {}
        self._strategy_sum_submitted: dict[str, float] = {}
        self._strategy_sum_filled: dict[str, float] = {}

    def update_metrics(
        self, order_event: dict[str, Any], fill_event: dict[str, Any]
    ) -> dict[str, Any]:
        r"""
        Produce a terminal performance report and compute execution metrological indices.

        Forensic Logic:
        1. Slippage Calculation: $S = Side \cdot (Price_{order} - Price_{fill})$.
           - Side Multiplier: 1.0 for BUY, -1.0 for SELL.
        2. Latency Measurement: $L = t_{fill} - t_{order}$.
        3. Fill Rate Computation: $F = FilledQuantity / SubmittedQuantity$.
        """
        monitoring_start = time.time()

        strategy_id = str(order_event.get("strategy_id", "GLOBAL_POOL"))
        side_label = str(order_event.get("side", "BUY")).upper()
        side_multiplier = 1.0 if side_label == "BUY" else -1.0

        # 1. Metrological Slippage Computation.
        order_price = float(order_event.get("price", 0.0))
        fill_price = float(fill_event.get("price", 0.0))
        calculated_slippage = side_multiplier * (order_price - fill_price)

        # 2. Sequential Latency Calibration.
        # Captures the time-delta between order submission and execution confirmation.
        t_order_raw = order_event.get("timestamp", monitoring_start)
        t_fill_raw = fill_event.get("timestamp", monitoring_start)
        execution_latency = max(0.0, float(t_fill_raw) - float(t_order_raw))

        # 3. Fill Rate aggregation.
        qty_submitted = float(order_event.get("quantity", 0.0))
        qty_filled = float(fill_event.get("quantity", 0.0))

        # Trace Indexing for institutional forensic audit.
        self._strategy_slippage_trace.setdefault(strategy_id, []).append(calculated_slippage)
        self._strategy_latency_trace.setdefault(strategy_id, []).append(execution_latency)
        self._strategy_sum_submitted[strategy_id] = (
            self._strategy_sum_submitted.get(strategy_id, 0.0) + qty_submitted
        )
        self._strategy_sum_filled[strategy_id] = (
            self._strategy_sum_filled.get(strategy_id, 0.0) + qty_filled
        )

        _LOG.info(
            f"[EXECUTION] PERFORMANCE_INDEXED | Strat: {strategy_id} "
            f"| Slippage: {calculated_slippage:.4f} | Latency: {execution_latency * 1000:.2f}ms"
        )

        # 4. Certification Artifact Construction.
        # Compute fill rate percentage for current strategy.
        cumulative_sub = self._strategy_sum_submitted[strategy_id]
        cumulative_fill = self._strategy_sum_filled[strategy_id]
        strategy_fill_rate = cumulative_fill / max(1e-8, cumulative_sub)

        artifact = {
            "status": "MONITORING_INDEXED",
            "metrics": {
                "absolute_execution_slippage": round(calculated_slippage, 6),
                "recorded_latency_ms": round(execution_latency * 1000, 4),
                "strategy_level_fill_rate": round(strategy_fill_rate, 4),
            },
            "forensics": {
                "order_price": order_price,
                "fill_price": fill_price,
                "side": side_label,
                "slippage_bps": (
                    round((calculated_slippage / order_price) * 10000, 2)
                    if order_price > 0
                    else 0.0
                ),
            },
            "certification": {
                "strategy_id": strategy_id,
                "timestamp": time.time(),
                "monitoring_overhead_ms": round((time.time() - monitoring_start) * 1000, 4),
            },
        }

        return artifact

    def get_execution_telemetry(self, strategy_id: str = "GLOBAL_POOL") -> dict[str, Any]:
        """
        situational awareness for institutional execution forensics.
        """
        slippage_history = self._strategy_slippage_trace.get(strategy_id, [])
        latency_history = self._strategy_latency_trace.get(strategy_id, [])

        avg_slippage = sum(slippage_history) / len(slippage_history) if slippage_history else 0.0
        avg_latency = sum(latency_history) / len(latency_history) if latency_history else 0.0

        total_sub = self._strategy_sum_submitted.get(strategy_id, 0.0)
        total_fill = self._strategy_sum_filled.get(strategy_id, 0.0)
        fill_rate_percentage = total_fill / total_sub * 100.0 if total_sub > 0 else 0.0

        return {
            "status": "EXECUTION_GOVERNANCE",
            "strategy": strategy_id,
            "avg_slippage_observed": round(avg_slippage, 6),
            "avg_latency_observed_ms": round(avg_latency * 1000, 4),
            "cumulative_fill_rate_pct": round(fill_rate_percentage, 2),
            "total_execution_events": len(slippage_history),
        }
