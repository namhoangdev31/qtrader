from __future__ import annotations

import logging
import statistics
import time
from typing import Any

_LOG = logging.getLogger("qtrader.certification.execution_consistency")


class ExecutionConsistencyValidator:
    r"""
    Principal Execution Consistency Validator.

    Objective: Ensure alignment between Signal intent, Order routing, and terminal
    Fill execution across the platform's trading lifecycle ($Signal \to Order \to Fill$).

    Model: Structural Lineage Verification with Error-Bound Gating.
    Constraint: Size and Timing Veracity ($\epsilon_{size} \le \dots, \epsilon_{time} \le \dots$).
    """

    def __init__(self, size_epsilon: float = 0.001, t_max_ms: float = 1000.0) -> None:
        """
        Initialize the institutional consistency controller.
        """
        self._size_eps = size_epsilon
        self._t_max = t_max_ms
        self._total_lineages_audited: int = 0
        self._mismatch_count: int = 0
        self._slippage_samples: list[float] = []

    def validate_execution_lineage(
        self,
        signals: list[dict[str, Any]],
        fills: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Produce a terminal execution consistency report for the terminal trade chain.

        Forensic Logic:
        1. Lineage Mapping: Bit-perfect mapping of signals to terminal fills using Lineage IDs.
        2. Side Verification: Ensures directionality alignment (Side Match).
        3. Size and Timing Gating: Validates that error bounds stay within institutional limits.
        4. Slippage Extraction: Quantifies the average execution impact for refined alpha modeling.
        """
        start_time = time.time()

        # 1. Structural Lineage Mapping.
        # Group signals and fills by their institutional lineage_id.
        lineage_map: dict[str, dict[str, dict[str, Any]]] = {}

        for _sig in signals:
            lineage_id = str(_sig.get("lineage_id", "UNKNOWN"))
            lineage_map[lineage_id] = {"signal": _sig}

        for _fill_rec in fills:
            lineage_id = str(_fill_rec.get("lineage_id", "UNKNOWN"))
            if lineage_id in lineage_map:
                lineage_map[lineage_id]["fill"] = _fill_rec
            else:
                _LOG.warning(f"[CONSISTENCY] ORPHAN_FILL_DETECTED | ID: {lineage_id}")

        audit_results = []
        perfect_alignment = True

        for lid, chain in lineage_map.items():
            signal: dict[str, Any] | None = chain.get("signal")
            fill: dict[str, Any] | None = chain.get("fill")

            if signal is None or fill is None:
                _LOG.error(f"[CONSISTENCY] SILENT_MISMATCH | Missing link for ID: {lid}")
                perfect_alignment = False
                self._mismatch_count += 1
                audit_results.append(
                    {"lineage_id": lid, "passed": False, "violation": "LINEAGE_BREAK"}
                )
                continue

            # Core Lineage Consistency Checks:
            # A. Direction Match (Side Verification).
            direction_passed = bool(signal["side"] == fill["side"])

            # B. Size Precision Gating ($\epsilon_{size} = |size_{signal} - size_{fill}|$).
            size_error = abs(float(signal["size"]) - float(fill["size"]))
            size_passed = size_error <= self._size_eps

            # C. Timing Latency Gating ($\epsilon_{time} = |t_{order} - t_{fill}|$).
            # Timestamps are in seconds.
            time_error_ms = abs(float(signal["timestamp"]) - float(fill["timestamp"])) * 1000
            timing_passed = time_error_ms <= self._t_max

            # D. Slippage Performance Derivation.
            # Assuming Absolute Slippage: (FillPrice - SignalPrice) * DirectionMultiplier.
            direction_mult = 1.0 if str(signal["side"]).upper() == "BUY" else -1.0
            slippage = (float(fill["price"]) - float(signal["price"])) * direction_mult
            self._slippage_samples.append(slippage)

            # Terminal Decision logic.
            passed = direction_passed and size_passed and timing_passed
            if not passed:
                perfect_alignment = False
                self._mismatch_count += 1

            audit_results.append(
                {
                    "lineage_id": lid,
                    "passed": passed,
                    "metrics": {
                        "size_error": round(size_error, 6),
                        "latency_ms": round(time_error_ms, 2),
                        "slippage": round(slippage, 6),
                    },
                }
            )

        self._total_lineages_audited += len(signals)
        current_mismatch_rate = (
            self._mismatch_count / self._total_lineages_audited
            if self._total_lineages_audited > 0
            else 0.0
        )
        avg_slippage = (
            statistics.mean(self._slippage_samples) if self._slippage_samples else 0.0
        )

        final_result = "PASS" if perfect_alignment else "FAIL"

        # Forensic Deployment Accounting.
        if perfect_alignment:
            _LOG.info(
                f"[CONSISTENCY] LINEAGE_VERIFIED | Count: {len(signals)} "
                f"| Avg Slippage: {avg_slippage:.6f}"
            )
        else:
            _LOG.error(
                f"[CONSISTENCY] LINEAGE_BREACH_DETECTED | Mismatch Rate: "
                f"{current_mismatch_rate * 100:.2f}%"
            )

        # 2. Certification Artifact Construction.
        artifact = {
            "status": "CONSISTENCY_COMPLETE",
            "result": final_result,
            "metrics": {
                "signals_audited": len(signals),
                "mismatch_rate_percent": round(current_mismatch_rate * 100, 4),
                "average_slippage_impact": round(avg_slippage, 6),
            },
            "lineage_audit": audit_results,
            "certification": {
                "size_epsilon_config": self._size_eps,
                "latency_limit_ms": self._t_max,
                "timestamp": time.time(),
                "real_validation_duration_ms": round((time.time() - start_time) * 1000, 4),
            },
        }

        return artifact

    def get_consistency_telemetry(self) -> dict[str, Any]:
        """
        situational awareness for institutional execution health.
        """
        avg_slippage = (
            statistics.mean(self._slippage_samples) if self._slippage_samples else 0.0
        )
        mismatch_rate = (
            (self._mismatch_count / self._total_lineages_audited * 100)
            if self._total_lineages_audited > 0
            else 0.0
        )
        return {
            "status": "EXECUTION_GOVERNANCE",
            "lifecycle_mismatch_rate": round(mismatch_rate, 2),
            "total_slippage_drift": round(avg_slippage, 6),
        }
