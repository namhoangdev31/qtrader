from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.portfolio.capital_flow")


class CapitalFlowManager:
    r"""
    Principal Treasury Control System.

    Objective: Handle deposits and withdrawals safely while maintaining bit-perfect
    consistency between the platform capital and trading state.

    Model: Flow Integrity ($Capital(t) = Capital(t-1) + Deposits - Withdrawals$).
    Constraint: Operational Solvency (Gated withdrawals during open risk).
    """

    def __init__(self) -> None:
        """
        Initialize the institutional capital flow manager.
        """
        # Telemetry for institutional situational awareness.
        self._cumulative_deposits: float = 0.0
        self._cumulative_withdrawals: float = 0.0
        self._denied_withdrawal_events: int = 0

    def process_flow_requests(
        self,
        current_capital: float,
        deposit_amount: float = 0.0,
        withdrawal_amount: float = 0.0,
        has_open_exposure: bool = False,
        permit_flow_during_risk: bool = False,
    ) -> dict[str, Any]:
        r"""
        Produce a terminal capital report and synchronize platform funding.

        Forensic Logic:
        1. Withdrawal Gating: Rejects outflows if open risk exists (Risk Integrity).
        2. Solvency Validation: Ensures withdrawals do not exceed total liquidity.
        3. Flow Recalculation: $Capital_{new} = Capital_{old} + NetFlow$.
        """
        execution_start = time.time()

        # 1. Metrological Validation and Gating.
        withdrawal_approved = True
        rejection_reason = "NONE"

        # Rule: No withdrawal during open risk (Protects margin and operational solvency).
        if withdrawal_amount > 0 and has_open_exposure and not permit_flow_during_risk:
            withdrawal_approved = False
            rejection_reason = "DENIED_OPEN_EXPOSURE"
            self._denied_withdrawal_events += 1

        # Rule: Solvency Verification.
        # Withdrawal cannot exceed the current available capital + new deposits.
        if withdrawal_approved and withdrawal_amount > (current_capital + deposit_amount):
            withdrawal_approved = False
            rejection_reason = "DENIED_INSUFFICIENT_LIQUIDITY"
            self._denied_withdrawal_events += 1

        approved_outflow = withdrawal_amount if withdrawal_approved else 0.0
        net_flow_basis = deposit_amount - approved_outflow
        updated_capital_state = current_capital + net_flow_basis

        # 2. Telemetry Persistence.
        if deposit_amount > 0:
            self._cumulative_deposits += deposit_amount
        if approved_outflow > 0:
            self._cumulative_withdrawals += approved_outflow

        if net_flow_basis != 0:
            _LOG.info(
                f"[CAPITAL_FLOW] FUNDING_UPDATED | Flow: {net_flow_basis:,.2f} "
                f"| Capital: {updated_capital_state:,.2f}"
            )

        # 3. Certification Artifact Construction.
        artifact = {
            "status": "FLOW_FINALIZED",
            "treasury": {
                "updated_net_capital": round(updated_capital_state, 4),
                "net_flow_basis": round(net_flow_basis, 4),
                "operational_solvency": round(updated_capital_state, 4),
            },
            "forensics": {
                "deposits_processed": round(deposit_amount, 4),
                "withdrawals_approved": round(approved_outflow, 4),
                "withdrawals_rejected": round(withdrawal_amount - approved_outflow, 4),
                "rejection_reason": rejection_reason,
            },
            "certification": {
                "historical_net_flow": round(
                    self._cumulative_deposits - self._cumulative_withdrawals, 4
                ),
                "timestamp": time.time(),
                "treasury_latency_ms": round((time.time() - execution_start) * 1000, 4),
            },
        }

        return artifact

    def get_flow_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional treasury control.
        """
        stable_event_limit = 5
        return {
            "status": "TREASURY_GOVERNANCE",
            "cumulative_funding_shift": round(
                self._cumulative_deposits - self._cumulative_withdrawals, 4
            ),
            "denied_withdrawal_events": self._denied_withdrawal_events,
            "liquidity_regime": (
                "STABLE"
                if self._denied_withdrawal_events < stable_event_limit
                else "CONSTRAINED_SOLVENCY"
            ),
        }
