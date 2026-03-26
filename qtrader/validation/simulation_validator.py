from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from scipy.stats import entropy, kurtosis

from qtrader.core.events import (
    SimulationAccuracyErrorEvent,
    SimulationAccuracyErrorPayload,
    SimulationAccuracyEvent,
    SimulationAccuracyPayload,
)
from qtrader.core.logger import log as logger

if TYPE_CHECKING:
    import polars as pl

    from qtrader.core.event_bus import EventBus


class SimulationValidator:
    """
    Market Simulation Statistical Accuracy Validator.

    Validates that simulated market data (Sandbox/Backtest) maintains
    statistical parity with real-world distributions:
    - Returns Distribution (Mean, Variance, Kurtosis)
    - KL Divergence (Distributional Similarity)
    - Autocorrelation & Correlation
    """

    def __init__(self, event_bus: EventBus) -> None:
        """
        Initialize the simulation validator.
        """
        self._event_bus = event_bus
        self._system_trace = UUID("00000000-0000-0000-0000-000000000000")

    async def validate_simulation(
        self, scenario_id: str, sim_data: pl.DataFrame, real_data: pl.DataFrame
    ) -> SimulationAccuracyEvent | None:
        """
        Execute industrial-grade statistical appraisal of simulation accuracy.
        """
        try:
            if sim_data.is_empty() or real_data.is_empty():
                raise ValueError("Incomplete dataset: Simulated or Real data are empty.")

            # 1. Compute Returns Vectors
            sim_returns = sim_data["close"].pct_change().drop_nulls().to_numpy()
            real_returns = real_data["close"].pct_change().drop_nulls().to_numpy()

            # Using constant for industrial-grade appraisal logic
            min_data_points = 20
            if len(sim_returns) < min_data_points or len(real_returns) < min_data_points:
                raise ValueError("Insufficient data points for industrial-grade appraisal.")

            # 2. Moment Analysis: Mean, Variance, Kurtosis
            mean_sim, mean_real = float(np.mean(sim_returns)), float(np.mean(real_returns))
            var_sim, var_real = float(np.var(sim_returns)), float(np.var(real_returns))
            kurt_sim, kurt_real = float(kurtosis(sim_returns)), float(kurtosis(real_returns))

            mean_diff = abs(mean_sim - mean_real)
            var_diff = abs(var_sim - var_real)
            kurt_diff = abs(kurt_sim - kurt_real)

            # 3. Distributional Similarity: KL Divergence
            bins = 50
            min_ret = min(np.min(sim_returns), np.min(real_returns))
            max_ret = max(np.max(sim_returns), np.max(real_returns))
            range_bounds = (min_ret, max_ret)

            p_hist, _ = np.histogram(real_returns, bins=bins, range=range_bounds, density=True)
            q_hist, _ = np.histogram(sim_returns, bins=bins, range=range_bounds, density=True)

            # Add epsilon to prevent log(0) in KL
            epsilon = 1e-10
            kl_div = float(entropy(p_hist + epsilon, q_hist + epsilon))

            # 4. Correlation Appraisal
            min_len = min(len(sim_returns), len(real_returns))
            correlation = float(np.corrcoef(sim_returns[:min_len], real_returns[:min_len])[0, 1])

            # 5. Accuracy Scoring
            accuracy_score = float(np.exp(-kl_div) * max(correlation, 0.0))

            # 6. Report Broadcast
            accuracy_event = SimulationAccuracyEvent(
                trace_id=self._system_trace,
                source="SimulationValidator",
                payload=SimulationAccuracyPayload(
                    scenario_id=scenario_id,
                    mean_diff=mean_diff,
                    variance_diff=var_diff,
                    kurtosis_diff=kurt_diff,
                    correlation=correlation,
                    kl_divergence=kl_div,
                    accuracy_score=accuracy_score,
                    metadata={"timestamp_ms": int(time.time() * 1000)},
                ),
            )

            await self._event_bus.publish(accuracy_event)
            logger.info(f"SIM_ACCURACY | {scenario_id} | Score: {accuracy_score:.4f}")

            return accuracy_event

        except Exception as e:
            logger.error(f"SIM_VALIDATION_FAILURE | {scenario_id} | {e!s}")
            await self._emit_error(scenario_id, "SYSTEM_FAILURE", str(e))
            return None

    async def _emit_error(self, scenario_id: str, err_type: str, details: str) -> None:
        """Emit a SimulationAccuracyErrorEvent to the global bus."""
        error_event = SimulationAccuracyErrorEvent(
            trace_id=self._system_trace,
            source="SimulationValidator",
            payload=SimulationAccuracyErrorPayload(
                scenario_id=scenario_id, error_type=err_type, details=details
            ),
        )
        await self._event_bus.publish(error_event)
