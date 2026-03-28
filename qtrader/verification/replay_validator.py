from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import polars as pl
from loguru import logger


@dataclass(slots=True)
class DivergencePoint:
    """Represents a specific point in time where states diverged."""
    offset: int
    timestamp: float
    field: str
    original_value: Any
    replay_value: Any


@dataclass(slots=True)
class ReplayReport:
    """Detailed report for the reproducibility validation trial."""
    status: str
    deterministic: bool
    total_steps: int
    divergence_score: int
    divergence_points: list[DivergencePoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "status": self.status,
            "deterministic": self.deterministic,
            "total_steps": self.total_steps,
            "divergence_score": self.divergence_score,
            "divergence_points": [
                {
                    "offset": d.offset,
                    "timestamp": d.timestamp,
                    "field": d.field,
                    "original": str(d.original_value),
                    "replay": str(d.replay_value)
                } for d in self.divergence_points
            ]
        }


class ReplayValidator:
    """
    Forensic engine for bit-perfect replay validation.
    
    Verifies that State_t == State'_t across all discrete time steps.
    """

    @staticmethod
    def compare_states(
        original_trajectory: list[dict[str, Any]], 
        replay_trajectory: list[dict[str, Any]]
    ) -> ReplayReport:
        """
        Perform bit-perfect comparison between two state trajectories.
        
        Args:
            original_trajectory: List of system state snapshots from the first run.
            replay_trajectory: List of system state snapshots from the second trial.
            
        Returns:
            ReplayReport summarizing the fidelity check.
        """
        divergences: list[DivergencePoint] = []
        total_steps = min(len(original_trajectory), len(replay_trajectory))
        
        if len(original_trajectory) != len(replay_trajectory):
            logger.warning(
                f"[REPLAY] Trajectory length mismatch! Original: {len(original_trajectory)} | Replay: {len(replay_trajectory)}"
            )

        for t in range(total_steps):
            orig_state = original_trajectory[t]
            repl_state = replay_trajectory[t]
            
            # Deep field comparison
            for key in orig_state:
                if key not in repl_state:
                    divergences.append(DivergencePoint(
                        offset=t,
                        timestamp=orig_state.get("timestamp", 0.0),
                        field=key,
                        original_value=orig_state[key],
                        replay_value="MISSING"
                    ))
                    continue
                
                v_orig = orig_state[key]
                v_repl = repl_state[key]
                
                if not ReplayValidator._is_equal(v_orig, v_repl):
                    divergences.append(DivergencePoint(
                        offset=t,
                        timestamp=orig_state.get("timestamp", 0.0),
                        field=key,
                        original_value=v_orig,
                        replay_value=v_repl
                    ))

        is_deterministic = len(divergences) == 0
        status = "PASS" if is_deterministic else "FAIL"
        
        if not is_deterministic:
            logger.error(f"[REPLAY] Divergence detected at step {divergences[0].offset} in field '{divergences[0].field}'")
        else:
            logger.success(f"[REPLAY] Bit-Perfect Replay Confirmed | Steps: {total_steps}")
            
        return ReplayReport(
            status=status,
            deterministic=is_deterministic,
            total_steps=total_steps,
            divergence_score=len(divergences),
            divergence_points=divergences
        )

    @staticmethod
    def _is_equal(a: Any, b: Any) -> bool:
        """
        Internal equality check for diverse data types (JSON-like, DataFrames, etc).
        """
        # 1. Polars DataFrame Comparison (Check first to avoid Series-based == issues)
        if isinstance(a, pl.DataFrame) and isinstance(b, pl.DataFrame):
            return a.equals(b)

        # 2. Exact Type/Value Match (handles int, str, bool, Decimal)
        try:
            if a == b:
                return True
        except (TypeError, ValueError):
            # Fallback for complex types that don't support simple ==
            pass
            
        # 3. Floating Point (Still exact, but handle NaN)
        if isinstance(a, float) and isinstance(b, float):
            import math
            if math.isnan(a) and math.isnan(b):
                return True
            return a == b
            
        # 4. Dictionary/List Comparison (Sort keys for JSON stability)
        if isinstance(a, (dict, list)) and isinstance(b, (dict, list)):
            try:
                return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
            except (TypeError, ValueError):
                return False
            
        return False

    @staticmethod
    def save_report(report: ReplayReport, output_path: str) -> None:
        """Serialize and save the replay report to disk."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"[REPLAY] Report archived at: {output_path}")
