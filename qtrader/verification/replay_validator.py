from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import polars as pl
from loguru import logger


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder for high-precision Decimal serialization."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


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
        """Convert report to JSON-serializable dictionary with high-precision stability."""
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
                    "original": d.original_value,
                    "replay": d.replay_value
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
        Internal bit-perfect equality check (ε=0).
        """
        # 1. Polars DataFrame Comparison
        if isinstance(a, pl.DataFrame) and isinstance(b, pl.DataFrame):
            return a.equals(b)

        # 2. Strict Decimal Comparison (No ε tolerance)
        if isinstance(a, Decimal) and isinstance(b, Decimal):
            return a == b

        # 3. Exact Type/Value Match
        try:
            # Note: We avoid 1.0 == Decimal('1.0') returning True if types must be sovereign
            if type(a) is not type(b):
                return False
            if a == b:
                return True
        except (TypeError, ValueError):
            pass
            
        # 4. Floating Point (Still exact, but handle NaN)
        if isinstance(a, float) and isinstance(b, float):
            import math
            if math.isnan(a) and math.isnan(b):
                return True
            return a == b
            
        # 5. Dictionary/List Comparison (Sovereign Serialization)
        if isinstance(a, (dict, list)) and isinstance(b, (dict, list)):
            try:
                # Use custom encoder to handle Decimal in nested structures
                s_a = json.dumps(a, sort_keys=True, cls=DecimalEncoder)
                s_b = json.dumps(b, sort_keys=True, cls=DecimalEncoder)
                return s_a == s_b
            except (TypeError, ValueError):
                return False
            
        return False

    @staticmethod
    def save_report(report: ReplayReport, output_path: str) -> None:
        """Serialize and save the replay report to disk."""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, cls=DecimalEncoder)
        logger.info(f"[REPLAY] Report archived at: {output_path}")
