from __future__ import annotations

import logging
from typing import Any

_LOG = logging.getLogger("qtrader.meta.constraint_engine")


class ConstraintEngine:
    """
    Quantitative Risk Systems Engine for hard-constraint strategy governance.

    Enforces deterministic filtering on strategy search spaces to prevent
    overfitting, operational instability, and risk-management violations.
    Calculates the constraint vector C = (risk, leverage, turnover, liquidity, complexity).
    """

    def __init__(  # noqa: PLR0913
        self,
        max_risk_vol: float = 0.40,
        max_mdd: float = 0.20,
        max_leverage: float = 5.0,
        max_turnover: float = 10.0,
        max_complexity: int = 20,
        max_adv_fraction: float = 0.05,
    ) -> None:
        """
        Initialize the governing thresholds for the industrial gate.

        Args:
            max_risk_vol: Maximum allowable annualized volatility (e.g. 0.40 = 40%).
            max_mdd: Maximum allowable Peak-to-Trough Drawdown (e.g. 0.20 = 20%).
            max_leverage: Maximum portfolio leverage (Absolute units).
            max_turnover: Maximum annualized turnover rate.
            max_complexity: Maximum number of internal parameters or signal inputs.
            max_adv_fraction: Maximum strategy size relative to Average Daily Volume.
        """
        self._max_risk_vol = max_risk_vol
        self._max_mdd = max_mdd
        self._max_leverage = max_leverage
        self._max_turnover = max_turnover
        self._max_complexity = max_complexity
        self._max_adv_fraction = max_adv_fraction

        # Governance Telemetry
        self.rejection_count = 0
        self.violation_counts: dict[str, int] = {
            "risk": 0,
            "turnover": 0,
            "liquidity": 0,
            "leverage": 0,
            "complexity": 0,
            "missing_data": 0,
        }

    def validate(self, strategy_metadata: dict[str, Any], metrics: dict[str, float]) -> bool:
        """
        Evaluate a candidate strategy against the locked constraint vector.

        Hard Rejection: A strategy failing even ONE constraint is rejected.
        """
        current_violations: list[str] = []

        try:
            # 1. Verification of Risk and Operational constraints
            current_violations.extend(self._check_risk_constraints(metrics))
            current_violations.extend(self._check_operational_constraints(metrics))
            current_violations.extend(self._check_complexity_constraints(strategy_metadata))

        except Exception as e:
            _LOG.error(f"Constraint evaluation failure: {e}")
            current_violations.append("missing_data")

        if not current_violations:
            return True

        self._record_rejections(current_violations)
        return False

    def _check_risk_constraints(self, metrics: dict[str, float]) -> list[str]:
        """Verify Volatility and Maximum Drawdown thresholds."""
        violations = []
        vol = metrics.get("volatility")
        mdd = metrics.get("max_drawdown")
        if vol is None or mdd is None:
            violations.append("missing_risk_data")
        elif vol > self._max_risk_vol or mdd > self._max_mdd:
            violations.append("risk")
        return violations

    def _check_operational_constraints(self, metrics: dict[str, float]) -> list[str]:
        """Verify Leverage, Turnover, and Liquidity (ADV) thresholds."""
        violations = []
        # Leverage
        lev = metrics.get("avg_leverage")
        if lev is None:
            violations.append("missing_leverage_data")
        elif lev > self._max_leverage:
            violations.append("leverage")

        # Turnover
        to = metrics.get("turnover")
        if to is None:
            violations.append("missing_turnover_data")
        elif to > self._max_turnover:
            violations.append("turnover")

        # Liquidity
        size = metrics.get("strategy_size")
        adv = metrics.get("avg_daily_volume")
        if size is None or adv is None:
            violations.append("missing_liquidity_data")
        elif adv > 0 and (size / adv) > self._max_adv_fraction:
            violations.append("liquidity")
        return violations

    def _check_complexity_constraints(self, metadata: dict[str, Any]) -> list[str]:
        """Verify model parameter and feature count thresholds."""
        violations = []
        complexity = int(metadata.get("num_parameters", 0))
        if complexity > self._max_complexity:
            violations.append("complexity")
        return violations

    def _record_rejections(self, current_violations: list[str]) -> None:
        """Update telemetry for rejection traceability."""
        self.rejection_count += 1
        for violation in current_violations:
            category = violation.replace("missing_", "").split("_")[0]
            if category in self.violation_counts:
                self.violation_counts[category] += 1
            else:
                self.violation_counts["missing_data"] += 1

        _LOG.warning(f"[REJECTION] Strategy failed constraints: {current_violations}")

    def get_observability_report(self) -> dict[str, Any]:
        """
        Generate a governance report for monitoring and compliance.

        Returns:
            Dictionary containing rejection rate and violation breakdown.
        """
        return {
            "status": "FILTERING",
            "passed": self.rejection_count == 0,
            "total_rejections": self.rejection_count,
            "violations": self.violation_counts,
        }
