from unittest.mock import MagicMock, patch
import pytest
from qtrader.ml.mlflow_manager import MLflowManager, PromotionConfig


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def manager_mocked(mock_client):
    with patch("qtrader.ml.mlflow_manager.MLFLOW_AVAILABLE", False):
        mgr = MLflowManager(enable_mlflow=False)
    mgr._client = mock_client
    mgr.enable_mlflow = True
    mgr._experiment_id = "exp_123"
    return mgr


def test_promote_if_better_than_production_no_production(manager_mocked, mock_client):
    shadow_run = MagicMock()
    shadow_run.data.metrics = {"sharpe_ratio": 1.5, "max_drawdown": 0.05, "hit_rate": 0.52}
    shadow_run.info.run_id = "shadow_run_123"
    mock_client.get_run.return_value = shadow_run
    mock_client.get_latest_versions.side_effect = [[], [MagicMock(version="1")]]
    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat",
        "shadow_run_123",
        PromotionConfig(sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5),
    )
    assert result is True
    mock_client.transition_model_version_stage.assert_called_once_with(
        name="strategy_TestStrat", version="1", stage="Production", archive_existing_versions=False
    )


def test_promote_if_better_than_production_better_than_production(manager_mocked, mock_client):
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
    mock_client.get_run.side_effect = [shadow_run, prod_run]
    mock_client.get_latest_versions.side_effect = [[prod_version], [staging_version]]
    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat",
        "shadow_run_123",
        PromotionConfig(sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5),
    )
    assert result is True
    assert mock_client.transition_model_version_stage.call_count == 1
    call = mock_client.transition_model_version_stage.call_args
    assert call.kwargs["version"] == "3"
    assert call.kwargs["stage"] == "Production"
    assert call.kwargs["archive_existing_versions"] is True


def test_promote_if_better_than_production_not_better_enough(manager_mocked, mock_client):
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
    mock_client.get_run.side_effect = [shadow_run, prod_run]
    mock_client.get_latest_versions.side_effect = [[prod_version], [staging_version]]
    result = manager_mocked._promote_if_better_than_production_sync(
        "TestStrat",
        "shadow_run_123",
        PromotionConfig(
            sharpe_threshold=1.0,
            drawdown_threshold=0.1,
            hit_rate_threshold=0.5,
            sharpe_improvement=0.2,
        ),
    )
    assert result is False
    promotion_calls = [
        call
        for call in mock_client.transition_model_version_stage.call_args_list
        if call.kwargs.get("stage") == "Production" and call.kwargs.get("version") == "3"
    ]
    assert len(promotion_calls) == 0
