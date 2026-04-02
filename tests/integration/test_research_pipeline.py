from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

from qtrader.backtest.integration import BacktestResult
from qtrader.backtest.tearsheet import TearsheetMetrics
from qtrader.pipeline.research import ResearchPipeline, ResearchResult


@pytest.fixture
def mock_pipeline_deps():
    return {
        "datalake": AsyncMock(),
        "feature_engine": MagicMock(),
        "alpha_engine": MagicMock(),
        "regime_detector": MagicMock(),
        "backtest_harness": MagicMock(),
        "model_registry": MagicMock(),
        "drift_monitor": MagicMock(),
    }

@pytest.mark.asyncio
async def test_research_pipeline_run_workflow(mock_pipeline_deps):
    # Setup mocks
    mock_df = pl.DataFrame({
        "timestamp": pl.datetime_range(datetime(2023,1,1), datetime(2023,1,1,10), interval="1h", eager=True),
        "symbol": ["BTC_USDT"] * 11,
        "close": [100.0] * 11
    })
    
    mock_pipeline_deps["datalake"].load.return_value = mock_df
    mock_pipeline_deps["feature_engine"].compute.return_value = mock_df.with_columns(pl.lit(0.1).alias("feat1"))
    mock_pipeline_deps["feature_engine"].compute_multi_symbol.return_value = mock_df.with_columns(pl.lit(0.1).alias("feat1"))
    mock_pipeline_deps["feature_engine"].get_all_feature_names.return_value = ["feat1"]
    
    alpha_df = pl.DataFrame({
        "timestamp": pl.datetime_range(datetime(2023,1,1), datetime(2023,1,1,10), interval="1h", eager=True),
        "momentum": [0.1]*11, 
        "composite_alpha": [0.1]*11,
        "close": [100.0]*11
    })
    mock_pipeline_deps["alpha_engine"].compute_all.return_value = alpha_df
    
    mock_pipeline_deps["regime_detector"].predict_regime.return_value = pl.Series("regime", [1]*11)
    mock_pipeline_deps["regime_detector"].predict_proba.return_value = pl.DataFrame({"regime_0": [0.1]*11, "regime_1": [0.9]*11})
    
    # Backtest result
    mock_metrics = MagicMock(spec=TearsheetMetrics)
    mock_metrics.sharpe_ratio = 1.5
    mock_metrics.max_drawdown = -0.05
    mock_metrics.win_rate = 0.6
    
    # ResearchPipeline uses these in Step 6 logic
    mock_bt_result = BacktestResult(
        strategy_name="momentum",
        tearsheet=mock_metrics,
        backtest_df=mock_df,
        html_report_path=None,
        analytics_metrics={}
    )
    mock_pipeline_deps["backtest_harness"].run.return_value = mock_bt_result

    # Mock regime stats
    mock_pipeline_deps["regime_detector"].get_regime_stats.return_value = pl.DataFrame()
    
    # Mock drift monitor
    mock_pipeline_deps["drift_monitor"].detect_drift.return_value = {"feat1": 0.5}

    pipeline = ResearchPipeline(
        datalake=mock_pipeline_deps["datalake"],
        feature_engine=mock_pipeline_deps["feature_engine"],
        alpha_engine=mock_pipeline_deps["alpha_engine"],
        regime_detector=mock_pipeline_deps["regime_detector"],
        backtest_harness=mock_pipeline_deps["backtest_harness"],
        model_registry=mock_pipeline_deps["model_registry"],
        drift_monitor=mock_pipeline_deps["drift_monitor"]
    )
    
    # Set model registry to return something
    mock_pipeline_deps["model_registry"].get_best_model.return_value = "best_run"

    # Run the pipeline
    with patch("qtrader.pipeline.research.BotConfig") as mock_bot_config:
        result = await pipeline.run(
            symbols=["BTC_USDT"],
            timeframe="1h",
            start_date="2023-01-01",
            end_date="2023-01-02",
            strategy_name="momentum",
            walk_forward=False # Simpler for now
        )
    
    assert isinstance(result, ResearchResult)
    assert result.approved_for_deployment is True
    mock_pipeline_deps["datalake"].load.assert_called()
    mock_pipeline_deps["backtest_harness"].run.assert_called_once()
