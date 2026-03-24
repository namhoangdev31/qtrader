import pytest
from unittest.mock import MagicMock, patch
from qtrader.ml.mlflow_manager import MLflowManager


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def manager_mocked(mock_client):
    """MLflowManager with real mlflow disabled but _client injected as mock."""
    with patch("qtrader.ml.mlflow_manager.MLFLOW_AVAILABLE", False):
        mgr = MLflowManager(enable_mlflow=False)
    # Manually inject mocked client and re-enable for targeted tests
    mgr._client = mock_client
    mgr.enable_mlflow = True
    mgr._experiment_id = "exp_123"
    return mgr


def test_promote_if_better_than_production_no_production(manager_mocked, mock_client):
    """Test promotion when there is no existing production model."""
    # Setup: shadow run meets absolute thresholds, no production model exists
    shadow_run = MagicMock()
    shadow_run.data.metrics = {"sharpe_ratio": 1.5, "max_drawdown": 0.05, "hit_rate": 0.52}
    shadow_run.info.run_id = "shadow_run_123"

    mock_client.get_run.return_value = shadow_run
    mock_client.get_latest_versions.side_effect = [
        [],  # No production versions
        [MagicMock(version="1")],  # One staging version
    ]

    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat", "shadow_run_123", 1.0, 0.1, 0.5, 0.0, 0.0, 0.0
    )

    assert result is True
    # Should have called transition_model_version_stage to promote the staging version to production
    mock_client.transition_model_version_stage.assert_called_once_with(
        name="strategy_TestStrat", version="1", stage="Production", archive_existing_versions=False
    )


def test_promote_if_better_than_production_better_than_production(manager_mocked, mock_client):
    """Test promotion when shadow run is better than production."""
    # Setup: shadow run meets absolute thresholds and is better than production
    shadow_run = MagicMock()
    shadow_run.data.metrics = {"sharpe_ratio": 1.5, "max_drawdown": 0.05, "hit_rate": 0.52}
    shadow_run.info.run_id = "shadow_run_123"

    prod_run = MagicMock()
    prod_run.data.metrics = {"sharpe_ratio": 1.0, "max_drawdown": 0.1, "hit_rate": 0.5}
    prod_run.info.run_id = "prod_run_456"

    prod_version = MagicMock()
    prod_version.version = "2"
    prod_version.run_id = "prod_run_456"

    staging_version = MagicMock()
    staging_version.version = "3"
    staging_version.run_id = "shadow_run_123"

    mock_client.get_run.side_effect = [
        shadow_run,
        prod_run,
    ]  # First call for shadow, second for production
    mock_client.get_latest_versions.side_effect = [
        [prod_version],  # Production query
        [staging_version],  # Staging query
    ]

    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat", "shadow_run_123", 1.0, 0.1, 0.5, 0.0, 0.0, 0.0
    )

    assert result is True
    # Should have promoted the staging version to production, archiving the existing production
    # With archive_existing_versions=True, this is done in a single call
    assert mock_client.transition_model_version_stage.call_count == 1
    call = mock_client.transition_model_version_stage.call_args
    # Call: promote staging version (v3) to production, archiving existing production (v2)
    assert call.kwargs["version"] == "3"
    assert call.kwargs["stage"] == "Production"
    assert call.kwargs["archive_existing_versions"] is True


def test_promote_if_better_than_production_not_better_enough(manager_mocked, mock_client):
    """Test that promotion doesn't happen when shadow run is not sufficiently better."""
    # Setup: shadow run meets absolute thresholds but is not better enough than production
    shadow_run = MagicMock()
    shadow_run.data.metrics = {"sharpe_ratio": 1.1, "max_drawdown": 0.09, "hit_rate": 0.51}
    shadow_run.info.run_id = "shadow_run_123"

    prod_run = MagicMock()
    prod_run.data.metrics = {"sharpe_ratio": 1.0, "max_drawdown": 0.1, "hit_rate": 0.5}
    prod_run.info.run_id = "prod_run_456"

    prod_version = MagicMock()
    prod_version.version = "2"
    prod_version.run_id = "prod_run_456"

    staging_version = MagicMock()
    staging_version.version = "3"
    staging_version.run_id = "shadow_run_123"

    mock_client.get_run.side_effect = [
        shadow_run,
        prod_run,
    ]  # First call for shadow, second for production
    mock_client.get_latest_versions.side_effect = [
        [prod_version],  # Production query
        [staging_version],  # Staging query
    ]

    # Require at least 0.2 improvement in Sharpe ratio
    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat", "shadow_run_123", 1.0, 0.1, 0.5, 0.2, 0.0, 0.0
    )

    assert result is False
    # Should not have called transition_model_version_stage for promotion
    # (might have been called for other reasons, but not for our promotion logic)
    # We can check that it wasn't called with the specific promotion parameters
    promotion_calls = [
        call
        for call in mock_client.transition_model_version_stage.call_args_list
        if call.kwargs.get("stage") == "Production" and call.kwargs.get("version") == "3"
    ]
    assert len(promotion_calls) == 0
