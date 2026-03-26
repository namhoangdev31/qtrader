from unittest.mock import AsyncMock

import numpy as np
import polars as pl
import pytest

from qtrader.core.events import EventType
from qtrader.validation.simulation_validator import SimulationValidator

# Test Constants
SCENARIO_ID = "BTC_SIM_V1"


@pytest.mark.asyncio
async def test_simulation_validator_compute_success() -> None:
    """Verify simulation accuracy computation with similar datasets."""
    # Set seed for deterministic forensic appraisal
    np.random.seed(42)

    bus = AsyncMock()
    validator = SimulationValidator(bus)

    # Use larger length to stabilize histograms for KL divergence
    length = 1000
    # 1. Real Data: Normal Distribution of returns
    real_returns = np.random.normal(0, 0.01, length)
    real_prices = 1000.0 * np.exp(np.cumsum(real_returns))
    real_df = pl.DataFrame({"close": real_prices})

    # 2. Simulated Data: Near-identical Distribution
    sim_returns = real_returns + np.random.normal(0, 0.0001, length)  # slight noise
    sim_prices = 1000.0 * np.exp(np.cumsum(sim_returns))
    sim_df = pl.DataFrame({"close": sim_prices})

    event = await validator.validate_simulation(SCENARIO_ID, sim_df, real_df)

    # 3. Validation of Accuracy Score
    assert event is not None  # noqa: S101
    # Accuracy Score = exp(-KL) * Correlation. Should be high for near-identical data.
    assert event.payload.accuracy_score > 0.8  # noqa: S101, PLR2004
    assert event.payload.kl_divergence < 0.20  # noqa: S101, PLR2004
    assert event.payload.correlation > 0.95  # noqa: S101, PLR2004

    # 4. Validation of Event Bus Publish
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.SIMULATION_ACCURACY_REPORT  # noqa: S101


@pytest.mark.asyncio
async def test_simulation_validator_insufficient_data() -> None:
    """Verify that insufficient data triggers a system failure."""
    bus = AsyncMock()
    validator = SimulationValidator(bus)

    sim_df = pl.DataFrame({"close": [100.0] * 5})
    real_df = pl.DataFrame({"close": [100.0] * 30})

    event = await validator.validate_simulation(SCENARIO_ID, sim_df, real_df)

    assert event is None  # noqa: S101
    assert bus.publish.called  # noqa: S101
    assert bus.publish.call_args[0][0].event_type == EventType.SIMULATION_ACCURACY_ERROR  # noqa: S101
    assert "Insufficient data" in str(bus.publish.call_args)  # noqa: S101
