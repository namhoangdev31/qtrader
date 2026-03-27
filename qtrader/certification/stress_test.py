from __future__ import annotations

import logging
import time
from enum import Enum, auto
from typing import Any

_LOG = logging.getLogger("qtrader.certification.stress_test")


class StressScenario(Enum):
    """
    Institutional Extreme Stress Scenarios.
    Defines the structural injection points for strategy robustness audits.
    """

    FLASH_CRASH = auto()
    VOLATILITY_SPIKE = auto()
    LIQUIDITY_DROP = auto()
    EXECUTION_DELAY = auto()


class StrategyStressValidator:
    """
    Principal Strategy Stress Validator.

    Objective: Validate platform structural robustness by ensuring that
    strategy $PnL$ remains within institutional bounds ($PnL \ge -Loss_{limit}$)
    across all extreme synthetic market stressors.

    Model: Worst-Case Gating with Scenario Synthetic Forensics.
    Constraint: Absolute Loss Survival ($Loss \le Loss_{limit}$).
    """

    def __init__(self, worst_case_loss_limit: float = 0.1) -> None:
        """
        Initialize the institutional stress controller.
        """
        self._limit = worst_case_loss_limit  # e.g., 0.1 for 10% max stress loss
        # Telemetry for institutional situational awareness.
        self._stats = {"worst_case_loss": 0.0, "scenario_failures_count": 0}

    def run_stress_audit(self, scenario_results: dict[StressScenario, float]) -> dict[str, Any]:
        """
        Produce a terminal strategy stress report for simulated extreme market events.

        Forensic Logic:
        1. Survival Evaluation: Audits the PnL of each scenario against the $Loss_{limit}$.
        2. Worst-Case Indexing: Tracks the absolute peak loss observed across the audit cycle.
        3. Mandatory Diversity: Returns FAIL if any mandated scenario breaches the limit.
        """
        start_time = time.time()

        # 1. Performance Evaluation across extreme stressors.
        # $Constraint: PnL_{stress} \ge -Loss_{limit}$
        scenario_evaluations = {}
        all_robustness_passed = True
        worst_observed_pnl = 1.0  # Initialize optimistically.

        for scenario, pnl in scenario_results.items():
            is_breach_detected = pnl < -self._limit
            if is_breach_detected:
                all_robustness_passed = False
                self._stats["scenario_failures_count"] += 1

            worst_observed_pnl = min(worst_observed_pnl, pnl)

            scenario_evaluations[scenario.name] = {
                "pnl": round(pnl, 6),
                "robustness_passed": not is_breach_detected,
            }

        # 2. Telemetry Update (Structural Solvency Tracking).
        peak_loss_percent = abs(min(worst_observed_pnl, 0.0))
        self._stats["worst_case_loss"] = max(self._stats["worst_case_loss"], peak_loss_percent)

        result_status = "PASS" if all_robustness_passed else "FAIL"

        # Forensic Deployment Accounting.
        if not all_robustness_passed:
            _LOG.error(
                f"[STRESS] ROBUSTNESS_BREACH | Worst Loss Observed: "
                f"{peak_loss_percent * 100:.2f}% | Limit: {self._limit * 100:.2f}%"
            )
        else:
            _LOG.info(f"[STRESS] ROBUSTNESS_PASS | peak_loss: {peak_loss_percent * 100:.2f}%")

        # 3. Certification Artifact Construction.
        artifact = {
            "status": "STRESS_COMPLETE",
            "result": result_status,
            "metrics": {
                "worst_case_loss_percent": round(peak_loss_percent, 6),
                "total_scenarios_audited": len(scenario_results),
                "successful_scenario_count": len(
                    [s for s in scenario_evaluations.values() if s["robustness_passed"]]
                ),
            },
            "scenario_breakdown": scenario_evaluations,
            "certification": {
                "institutional_loss_limit": self._limit,
                "timestamp": time.time(),
                "real_execution_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_stress_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional strategy robustness.
        """
        return {
            "status": "STRESS_HEALTH",
            "peak_stress_loss_observed": round(self._stats["worst_case_loss"], 6),
            "cumulative_scenario_failures": self._stats["scenario_failures_count"],
        }
