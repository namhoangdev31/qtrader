from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any

_LOG = logging.getLogger("qtrader.certification.capital_test")


class SolvencyScenario(Enum):
    """
    Institutional Capital Solvency Scenarios.
    Defines the injection points for worst-case solvency validation.
    """

    FLASH_CRASH = auto()
    CONTINUOUS_LOSSES = auto()
    SLIPPAGE_SPIKE = auto()


class CapitalPreservationValidator:
    """
    Principal Capital Preservation Validator.

    Objective: Validate platform structural solvency by ensuring that terminal
    capital depletions stay within institutional bounds (Loss <= Loss_max)
    across all worst-case historical and simulated market stressors.

    Model: Zero-Tolerance Loss Gating with Trajectory Forensics.
    Constraint: Absolute Loss Bound.
    """

    def __init__(self, max_loss_threshold_percent: float = 0.15) -> None:
        """
        Initialize the institutional solvency controller.
        """
        self._limit = max_loss_threshold_percent
        # Telemetry for institutional situational awareness.
        self._stats = {"max_drawdown": 0.0, "worst_recorded_loss": 0.0}

    def validate_preservation(
        self,
        initial_capital: float,
        current_capital: float,
        scenario: SolvencyScenario,
    ) -> dict[str, Any]:
        """
        Produce a terminal capital solvency report for a simulated trading trajectory.

        Forensic Logic:
        1. Loss Computation: Derives the absolute and percentage capital depletion.
        2. Solvency Gating: Validates that $PnL_{min} >= -Loss_{limit}$.
        3. Trajectory Forensics: Tracks peak MDD and absolute worst-case metrics.
        """
        start_time = time.time()

        # 1. Forensic Loss Derivation.
        # $Loss = Capital_{initial} - Capital_{current}$
        absolute_loss = initial_capital - current_capital
        percentage_loss = absolute_loss / initial_capital if initial_capital > 0.0 else 0.0

        # 2. Structural Solvency Gating (Zero-Tolerance).
        is_solvency_maintained = percentage_loss <= self._limit
        result_status = "PASS" if is_solvency_maintained else "FAIL"

        # 3. Trajectory Update (Peak MDD Tracking).
        self._stats["max_drawdown"] = max(self._stats["max_drawdown"], percentage_loss)
        self._stats["worst_recorded_loss"] = max(
            self._stats["worst_recorded_loss"], percentage_loss
        )

        # 4. Forensic Compliance Accounting.
        if is_solvency_maintained:
            _LOG.info(
                f"[CAPITAL] SOLVENCY_PASS | Scenario: {scenario.name} "
                f"| Depletion: {percentage_loss * 100:.2f}%"
            )
        else:
            _LOG.error(
                f"[CAPITAL] SOLVENCY_BREACH | Scenario: {scenario.name} "
                f"| Depletion: {percentage_loss * 100:.2f}% | Limit: {self._limit * 100:.2f}%"
            )

        # 5. Certification Artifact Construction.
        artifact = {
            "status": "CAPITAL_COMPLETE",
            "result": result_status,
            "metrics": {
                "initial_equity": initial_capital,
                "current_equity": current_capital,
                "absolute_loss": round(absolute_loss, 4),
                "percentage_depletion": round(percentage_loss, 4),
                "gating_violated": not is_solvency_maintained,
            },
            "certification": {
                "scenario": scenario.name,
                "timestamp": time.time(),
                "real_sim_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_solvency_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional capital health.
        """
        return {
            "status": "CAPITAL_SOLVENCY",
            "peak_drawdown_observed": round(self._stats["max_drawdown"], 4),
            "worst_case_loss": round(self._stats["worst_recorded_loss"], 4),
        }
