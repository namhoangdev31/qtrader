from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from qtrader.alpha.factory import AlphaFactory


@pytest.fixture
def mock_engine() -> MagicMock:
    """Mock for FactorEngine."""
    engine = MagicMock()
    # Return 10 rows for clustering stability if needed
    engine.compute.return_value = pl.DataFrame(
        {
            "timestamp": [i for i in range(10)],
            "f1": [0.1 * i for i in range(10)],
            "f2": [0.5 - 0.01 * i for i in range(10)],
        }
    )
    return engine


@pytest.fixture
def mock_registry() -> MagicMock:
    """Mock for ModelRegistry."""
    registry = MagicMock()
    registry.log_model_iteration.return_value = "run_abc_123"
    return registry


@pytest.fixture
def mock_selector() -> MagicMock:
    """Mock for AlphaMetaSelector."""
    return MagicMock()


def test_alpha_factory_pipeline_flow(
    mock_engine: MagicMock, mock_registry: MagicMock, mock_selector: MagicMock
) -> None:
    """Verify that the full factory pipeline executes all stages in order."""
    factory = AlphaFactory(mock_engine, mock_registry, mock_selector)

    raw_data = pl.DataFrame(
        {
            "timestamp": [i for i in range(10)],
            "open": [100.0] * 10,
            "high": [105.0] * 10,
            "low": [95.0] * 10,
            "close": [100.0] * 10,
            "volume": [1000] * 10,
            "returns": [0.01 * (1 if i % 2 == 0 else -1) for i in range(10)],
        }
    )

    # Use patch to avoid heavy LightGBM training and verify core logic
    with (
        patch("qtrader.alpha.factory.GBDTAlphaModel") as mock_model_cls,
        patch("qtrader.alpha.factory.InteractionGenerator.generate") as mock_gen,
    ):
        # Setup mock model instance
        mock_instance = MagicMock()
        mock_instance.evaluate.return_value = {"ic": 0.05, "mse": 0.001}
        mock_instance.predict.return_value = [0.01] * 10
        mock_instance.model = MagicMock()  # Underlying lightgbm instance
        mock_model_cls.return_value = mock_instance

        # Setup mock interaction generator
        mock_gen.side_effect = lambda df, cols: df

        # Run pipeline
        run_ids = factory.run_discovery_pipeline(raw_data, target_col="returns")

        # Assertions
        assert len(run_ids) == 1
        assert run_ids[0] == "run_abc_123"

        # Check stage invocations
        mock_engine.compute.assert_called_once()
        mock_gen.assert_called_once()
        mock_model_cls.assert_called_once()
        mock_instance.fit.assert_called_once()
        mock_instance.evaluate.assert_called_once()
        mock_registry.log_model_iteration.assert_called_once()


def test_alpha_factory_empty_input_protection(
    mock_engine: MagicMock, mock_registry: MagicMock, mock_selector: MagicMock
) -> None:
    """Verify factory handles empty input gracefully."""
    factory = AlphaFactory(mock_engine, mock_registry, mock_selector)
    empty_df = pl.DataFrame()

    runs = factory.run_discovery_pipeline(empty_df)
    assert runs == []
    mock_registry.log_model_iteration.assert_not_called()
