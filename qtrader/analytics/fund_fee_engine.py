from __future__ import annotations

import logging
import time
from decimal import Decimal
from typing import Any

from qtrader.core.decimal_adapter import d

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
        self._total_fees_collected_historical: Decimal = d(0)
        self._peak_hwm_observed: Decimal = d(0)
        self._fee_valuation_cycles: int = 0

    def calculate_operational_fees(
        self,
        current_nav: Decimal,
        current_pnl: Decimal,
        current_hwm: Decimal,
        mgmt_rate_bps: Decimal = d("200.0"),
        perf_rate_pct: Decimal = d("20.0"),
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
        mgmt_scalar = mgmt_rate_bps / d("10000.0")
        perf_scalar = perf_rate_pct / d("100.0")

        # 2. Management Fee Computation.
        management_fee = current_nav * mgmt_scalar

        # 3. Performance Fee Computation (HWM Interaction).
        # We only charge performance fee on profit that is strictly above the historical peak.
        profit_delta_above_hwm = max(d(0), current_pnl - current_hwm)
        performance_fee = profit_delta_above_hwm * perf_scalar

        total_fee = management_fee + performance_fee
        new_hwm_basis = max(current_hwm, current_pnl)

        # 4. Telemetry Persistence.
        self._fee_valuation_cycles += 1
        self._total_fees_collected_historical += total_fee
        self._peak_hwm_observed = max(self._peak_hwm_observed, new_hwm_basis)

        _LOG.info(
            f"[FEES] CALCULATION_FINALIZED | Total: {total_fee} "
            f"| HWM: {new_hwm_basis} | Cycles: {self._fee_valuation_cycles}"
        )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "FEE_ALLOCATION_FINALIZED",
            "fees": {
                "total_management_fee": management_fee,
                "total_performance_fee": performance_fee,
                "institutional_total": total_fee,
            },
            "hwm_forensics": {
                "previous_hwm_basis": current_hwm,
                "updated_hwm_basis": new_hwm_basis,
                "taxable_profit_delta": profit_delta_above_hwm,
            },
            "certification": {
                "cumulative_fees_historical": self._total_fees_collected_historical,
                "timestamp": time.time(),
                "valuation_latency_ms": (time.time() - valuation_start) * 1000,
            },
        }

        return artifact

    def get_fee_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional operational fee governance.
        """
        return {
            "status": "FEE_GOVERNANCE",
            "total_fees_accumulated": self._total_fees_collected_historical,
            "peak_hwm_observed": self._peak_hwm_observed,
            "fee_valuation_cycles": self._fee_valuation_cycles,
        }
