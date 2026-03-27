from __future__ import annotations

import logging
import time
from typing import Any

_LOG = logging.getLogger("qtrader.analytics.fee_engine")


class FeeCalculationEngine:
    r"""
    Principal Operational Fee Governance System.

    Objective: Compute management and performance fees while strictly enforcing
    High-Water Mark (HWM) principles to ensure fair fund administration.

    Model: HWM-Gated Performance Fees ($Fee_p = \max(PnL - HWM, 0) \cdot rate_p$).
    Verification: Total Collection ($TotalFee = Fee_m + Fee_p$).
    """

    def __init__(self) -> None:
        """
        Initialize the institutional fee calculation engine.
        """
        # Telemetry for institutional situational awareness.
        self._total_fees_collected_historical: float = 0.0
        self._peak_hwm_observed: float = 0.0
        self._fee_valuation_cycles: int = 0

    def calculate_operational_fees(
        self,
        current_nav: float,
        current_pnl: float,
        current_hwm: float,
        mgmt_rate_bps: float = 200.0,
        perf_rate_pct: float = 20.0,
    ) -> dict[str, Any]:
        r"""
        Produce a terminal fee report and update High-Water Mark (HWM) basis.

        Forensic Logic:
        1. Management Fee ($Fee_m$): $NAV \cdot (mgmt\_rate\_bps / 10000)$.
        2. Performance Fee ($Fee_p$): $\max(PnL - HWM, 0) \cdot (rate\_p / 100)$.
        3. High-Water Mark Update: $HWM_{new} = \max(HWM_{old}, PnL)$.
        4. Operational Transparency: Logs all fees with forensic attribution level.
        """
        valuation_start = time.time()

        # 1. Metrological Constants.
        mgmt_scalar = mgmt_rate_bps / 10000.0
        perf_scalar = perf_rate_pct / 100.0

        # 2. Management Fee Computation.
        management_fee = current_nav * mgmt_scalar

        # 3. Performance Fee Computation (HWM Interaction).
        # We only charge performance fee on profit that is strictly above the historical peak.
        profit_delta_above_hwm = max(0.0, current_pnl - current_hwm)
        performance_fee = profit_delta_above_hwm * perf_scalar

        total_fee = management_fee + performance_fee
        new_hwm_basis = max(current_hwm, current_pnl)

        # 4. Telemetry Persistence.
        self._fee_valuation_cycles += 1
        self._total_fees_collected_historical += total_fee
        self._peak_hwm_observed = max(self._peak_hwm_observed, new_hwm_basis)

        _LOG.info(
            f"[FEES] CALCULATION_FINALIZED | Total: {total_fee:,.2f} "
            f"| HWM: {new_hwm_basis:,.2f} | Cycles: {self._fee_valuation_cycles}"
        )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "FEE_ALLOCATION_FINALIZED",
            "fees": {
                "total_management_fee": round(management_fee, 4),
                "total_performance_fee": round(performance_fee, 4),
                "institutional_total": round(total_fee, 4),
            },
            "hwm_forensics": {
                "previous_hwm_basis": round(current_hwm, 4),
                "updated_hwm_basis": round(new_hwm_basis, 4),
                "taxable_profit_delta": round(profit_delta_above_hwm, 4),
            },
            "certification": {
                "cumulative_fees_historical": round(self._total_fees_collected_historical, 4),
                "timestamp": time.time(),
                "valuation_latency_ms": round((time.time() - valuation_start) * 1000, 4),
            },
        }

        return artifact

    def get_fee_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional operational fee governance.
        """
        return {
            "status": "FEE_GOVERNANCE",
            "total_fees_accumulated": round(self._total_fees_collected_historical, 4),
            "peak_hwm_observed": round(self._peak_hwm_observed, 4),
            "fee_valuation_cycles": self._fee_valuation_cycles,
        }
