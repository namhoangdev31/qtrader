from __future__ import annotations

import hashlib
import logging
import time
from typing import Any, Final, cast

import numpy as np
import polars as pl

_LOG = logging.getLogger("qtrader.compliance.risk_disclosure")


class RiskReportingEngine:
    """
    Principal Risk Reporting Engine.

    Objective: Generate deterministic, reproducible, and auditable risk
    disclosure reports for the QTrader platform.
    Computes institutional metrics (VaR, MaxDD, Volatility) using structural
    vectorized logic on portfolio datasets.
    """

    def __init__(self, reporting_id: str = "GENERIC_OVERSIGHT") -> None:
        """
        Initialize the institutional reporting engine.
        """
        self._id: Final[str] = reporting_id

        # Telemetry for situational awareness.
        self._stats = {"reports_generated": 0}

    def generate_disclosure(
        self,
        equity_curve: list[float],
        returns: list[float],
    ) -> dict[str, Any]:
        """
        Extract institutional risk measures from platform performance vectors.

        Computation Strategy:
        1. Polars Vectorization: Ensures high-performance return analysis.
        2. Parametric VaR: z-score based tail risk calculation (99% confidence).
        3. Peak-to-Trough Trajectory: Continuous drawdown tracking.
        4. Data Fingerprinting: SHA-256 hashing for reproducibility audit.
        """
        start_time = time.time()

        # Vectorized baseline initialization.
        s_equity = pl.Series("equity", equity_curve)
        s_returns = pl.Series("returns", returns)

        # 1. Deterministic Audit Identity.
        fingerprint = hashlib.sha256(str(equity_curve).encode()).hexdigest()[:12]

        # 2. Value at Risk Analysis (VaR 99% 1-Day).
        # Formula: z * sigma * sqrt(t). z-score(99%) = 2.326.
        sigma = s_returns.std() if len(s_returns) > 1 else 0.0
        var_99 = 2.326 * (sigma if sigma is not None else 0.0)

        # 3. Maximum Drawdown Calculation.
        if len(s_equity) > 0:
            peak = s_equity.cum_max()
            drawdowns = (peak - s_equity) / peak
            max_dd = drawdowns.max()
        else:
            max_dd = 0.0

        # 4. Annualized Volatility Tracking.
        # sigma * sqrt(252 trading days).
        vol_ann = (sigma if sigma is not None else 0.0) * np.sqrt(252)

        # Industrial Report Payload construction.
        report = {
            "status": "DISCLOSURE",
            "reporting_id": self._id,
            "data_fingerprint": fingerprint,
            "metrics": {
                "VaR_99": round(cast("float", var_99), 6),
                "Max_DD": round(float(cast("float", max_dd if max_dd is not None else 0.0)), 6),
                "Annualized_Vol": round(cast("float", vol_ann), 6),
                "Sample_Size": len(s_equity),
            },
            "timestamp": time.time(),
            "latency_ms": round((time.time() - start_time) * 1000, 2),
        }

        self._stats["reports_generated"] += 1
        _LOG.info(f"[DISCLOSURE] REPORT_GENERATED | ID: {self._id} | Fingerprint: {fingerprint}")
        return report

    def get_audit_stats(self) -> dict[str, Any]:
        """
        situational awareness for institutional reporting cycles.
        """
        return {
            "status": "AUDIT",
            "generation_count": self._stats["reports_generated"],
        }
