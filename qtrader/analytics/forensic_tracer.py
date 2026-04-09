from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from qtrader.core.dynamic_config import config_manager
from qtrader.core.latency_enforcer import latency_enforcer

logger = logging.getLogger("qtrader.analytics.forensic")


class ForensicTracer:
    """Consolidates forensic telemetry from all sub-engines for dashboard synchronization.

    This decoupling ensures that generating complex traces doesn't slow down
    the main high-frequency execution path.
    """

    def __init__(self) -> None:
        pass

    def aggregate_traces(
        self,
        symbol: str,
        ml_result: dict[str, Any],
        broker_quotes: dict[str, Any],
        kill_switch: Any,
        guardrail_manager: Any,
        allocator: Any,
        recon: Any,
        state: Any,
    ) -> dict[str, Any]:
        """Aggregate traces from all specialized decision engines."""
        latencies = latency_enforcer.get_current_measurements()
        recon_audit = recon.get_last_audit() if hasattr(recon, "get_last_audit") else {}
        from qtrader.core.config import settings

        quote = broker_quotes.get(symbol, {})
        live_price = float(quote.get("price") or settings.ts_reference_price)

        return {
            "ingestion": {
                "price": live_price,
                "timestamp": datetime.now().isoformat(),
                "status": "OK" if quote.get("price") else "WAITING",
            },
            "AlphaEngine": {
                **ml_result,
                "latency_ms": latencies.get("alpha_computation", {}).get("duration_ms", 0.0),
                "budget_ms": latencies.get("alpha_computation", {}).get("budget_ms", 5.0),
                "prediction_type": "FORENSIC" if ml_result.get("chronos") else "TECHNICAL",
            },
            "RiskEngine": {
                **(kill_switch.get_trace() if hasattr(kill_switch, "get_trace") else {}),
                "latency_ms": latencies.get("risk_check", {}).get("duration_ms", 0.0),
                "status": "HALTED"
                if (hasattr(kill_switch, "is_system_halted") and kill_switch.is_system_halted())
                else "OK",
            },
            "RiskGuard": {
                **(
                    guardrail_manager.get_trace() if hasattr(guardrail_manager, "get_trace") else {}
                ),
                "latency_ms": latencies.get("signal_generation", {}).get("duration_ms", 0.0),
            },
            "Portfolio": {
                **(allocator.get_trace() if hasattr(allocator, "get_trace") else {}),
                "latency_ms": latencies.get("portfolio_allocation", {}).get("duration_ms", 0.0),
            },
            "Reconciliation": {
                **recon_audit,
                "status": "DANGER" if (recon_audit.get("mismatch_count", 0) > 0) else "OK",
            },
            "StrategyState": {
                "streak": state.signal_streak.get(symbol, 0),
                "last_direction": state.last_signal_direction.get(symbol, "NONE"),
                "cooldown": state.loss_cooldown.get(symbol, 0),
                "is_circuit_broken": state.consecutive_losses
                >= config_manager.get("MAX_CONSECUTIVE_LOSSES", 5),
            },
        }
