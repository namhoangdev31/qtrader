from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.capital_guard")


class CapitalPreservationGuard:
    """
    Principal Capital Preservation Guard.

    Objective: Enforce terminal capital integrity by halting all platform activity
    if total portfolio loss exceeds the institutional hard limit.

    Model: Binary Operational Gating (SAFE / HALT).
    Constraint: Hard Stop (Non-override response).
    """

    def __init__(self) -> None:
        """
        Initialize the institutional hard-loss guard.
        """
        # Telemetry for institutional situational awareness.
        self._cumulative_halt_count: int = 0
        self._historical_peak_loss: float = 0.0

    def check_integrity(
        self, initial_capital: float, current_capital: float, loss_limit: float
    ) -> dict[str, Any]:
        """
        Produce a terminal integrity report and check the hard loss threshold.

        Forensic Logic:
        1. Loss Computation: $Loss = InitialCapital - CurrentCapital$.
        2. Binary Gating: If $Loss > Loss_{limit} \implies$ Status = HALT.
        3. Industrial Protection: Breach triggers immediate operational lockout.
        """
        start_time = time.time()

        # 1. Industrial Loss Computation ($Loss = Initial - Current$).
        # Loss must be strictly represent depletion of the initial base.
        raw_loss = initial_capital - current_capital
        absolute_loss = max(0.0, raw_loss)

        # 2. Terminal Threshold Verification.
        is_breach_active = absolute_loss > loss_limit
        guard_status = "SAFE"
        validation_code = "PASS"

        if is_breach_active:
            guard_status = "HALT"
            validation_code = "BREACHED"
            self._cumulative_halt_count += 1
            _LOG.critical(
                f"[CAPITAL_GUARD] BREACH_DETECTED | Loss: {absolute_loss:.2f} "
                f"| Limit: {loss_limit:.2f}"
            )
        else:
            _LOG.info(
                f"[CAPITAL_GUARD] INTEGRITY_OK | Loss: {absolute_loss:.2f} "
                f"| Limit: {loss_limit:.2f}"
            )

        # Forensic Peak Loss Tracking.
        self._historical_peak_loss = max(self._historical_peak_loss, absolute_loss)

        # 3. Certification Artifact Construction.
        artifact = {
            "status": "CAPITAL_INTEGRITY_INDEXED",
            "result": validation_code,
            "guard_state": guard_status,
            "metrics": {
                "absolute_capital_loss": round(absolute_loss, 4),
                "remaining_risk_budget": round(max(0.0, loss_limit - absolute_loss), 4),
                "halt_event_count": self._cumulative_halt_count,
            },
            "certification": {
                "initial_funding_base": initial_capital,
                "institutional_loss_limit": loss_limit,
                "current_equity_snapshot": current_capital,
                "timestamp": time.time(),
                "guard_latency_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_guard_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional capital protection.
        """
        return {
            "status": "CAPITAL_GOVERNANCE",
            "total_halt_events": self._cumulative_halt_count,
            "historical_peak_loss": round(self._historical_peak_loss, 4),
            "protection_active": self._cumulative_halt_count > 0,
        }
