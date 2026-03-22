"""Integration test for the QTrader pipeline components.

This test verifies that the pipeline components can be instantiated and
work together at a basic level, using mocks where necessary.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl

# Import the pipeline components we implemented
from qtrader.pipeline.research import ResearchPipeline, ResearchResult
from qtrader.pipeline.deployment import DeploymentBridge
from qtrader.backtest.integration import BacktestHarness, BacktestResult
from qtrader.output.bot.config import BotConfig
from qtrader.output.analytics.tearsheet import TearsheetMetrics
from qtrader.output.analytics.drift import DriftMonitor
from qtrader.output.analytics.performance import PerformanceAnalytics
from qtrader.ml.registry import ModelRegistry
from qtrader.ml.walk_forward import WalkForwardPipeline
from qtrader.input.features.engine import FactorEngine
from qtrader.input.alpha.registry import AlphaEngine
from qtrader.ml.regime_detector import RegimeDetector
from qtrader.backtest.engine_vectorized import VectorizedEngine
from qtrader.backtest.tearsheet import TearsheetGenerator
from qtrader.input.data.datalake import DataLake
from qtrader.core.event_bus import EventBus


async def test_research_pipeline_with_mocks():
    """Test ResearchPipeline with mocked dependencies."""
    print("Testing ResearchPipeline with mocks...")
    
    # Create mock dependencies
    mock_datalake = AsyncMock(spec=DataLake)
    mock_feature_engine = MagicMock(spec=FactorEngine)
    mock_alpha_engine = MagicMock(spec=AlphaEngine)
    mock_regime_detector = MagicMock(spec=RegimeDetector)
    mock_backtest_harness = MagicMock(spec=BacktestHarness)
    mock_model_registry = MagicMock(spec=ModelRegistry)
    mock_drift_monitor = MagicMock(spec=DriftMonitor)
    
    # Set up mock return values
    # Mock data lake to return a simple DataFrame
    mock_df = pl.DataFrame({
        "timestamp": pl.date_range("2023-01-01", periods=10, interval="1d"),
        "symbol": ["AAPL"] * 10,
        "open": [100.0] * 10,
        "high": [105.0] * 10,
        "low": [95.0] * 10,
        "close": [102.0] * 10,
        "volume": [1000.0] * 10
    })
    mock_datalake.load.return_value = mock_df
    
    # Mock feature engine
    mock_feature_engine.get_all_feature_names.return_value = ["rsi", "macd"]
    mock_feature_engine.compute.return_value = pl.DataFrame({
        "timestamp": pl.date_range("2023-01-01", periods=10, interval="1d"),
        "rsi": [50.0] * 10,
        "macd": [0.5] * 10
    })
    mock_feature_engine.store = MagicMock()
    mock_feature_engine.store.save_features = MagicMock()
    
    # Mock alpha engine
    mock_alpha_engine.compute_all.return_value = pl.DataFrame({
        "timestamp": pl.date_range("2023-01-01", periods=10, interval="1d"),
        "symbol": ["AAPL"] * 10,
        "momentum_alpha": [0.1] * 10,
        "mean_reversion_alpha": [-0.1] * 10,
        "composite_alpha": [0.05] * 10
    })
    
    # Mock regime detector
    mock_regime_detector.predict_regime.return_value = pl.Series([0, 0, 1, 1, 0, 0, 1, 1, 0, 0])
    mock_regime_detector.predict_proba.return_value = pl.DataFrame({
        "regime_0": [0.8] * 10,
        "regime_1": [0.2] * 10
    })
    
    # Mock backtest harness
    mock_tearsheet = TearsheetMetrics(
        total_return=0.15,
        ann_return=0.12,
        ann_volatility=0.18,
        sharpe_ratio=0.67,
        sortino_ratio=0.8,
        calmar_ratio=0.5,
        omega_ratio=1.2,
        max_drawdown=0.08,
        max_dd_duration_days=10,
        avg_dd_duration_days=5.0,
        recovery_time_days=15.0,
        total_trades=10,
        win_rate=0.6,
        avg_win_pct=0.02,
        avg_loss_pct=0.015,
        profit_factor=1.33,
        expected_value=0.005,
        avg_turnover_daily=0.1,
        total_cost_pct=0.02,
        skewness=0.1,
        kurtosis=0.2
    )
    
    mock_backtest_result = BacktestResult(
        strategy_name="momentum",
        tearsheet=mock_tearsheet,
        backtest_df=pl.DataFrame({
            "timestamp": pl.date_range("2023-01-01", periods=10, interval="1d"),
            "symbol": ["AAPL"] * 10,
            "close": [102.0] * 10,
            "equity_curve": [100000.0 * (1 + 0.001 * i) for i in range(10)],
            "drawdown": [0.0] * 10
        }),
        html_report_path=None,
        analytics_metrics={"sharpe_ratio": 0.67, "win_rate": 0.6}
    )
    mock_backtest_harness.run.return_value = mock_backtest_result
    
    # Mock model registry
    mock_model = MagicMock()
    mock_model.fit = MagicMock()
    mock_model.predict = MagicMock(return_value=[0.01] * 5)
    mock_model_registry.get_model.return_value = mock_model
    
    # Mock drift monitor
    mock_drift_monitor.detect_drift.return_value = {"rsi": 0.05, "macd": 0.03}
    
    # Mock walk-forward pipeline
    with patch('qtrader.pipeline.research.WalkForwardPipeline') as mock_wf_class:
        mock_wf_instance = MagicMock()
        mock_wf_instance.get_splits.return_value = [
            (pl.DataFrame({"a": [1, 2, 3]}), pl.DataFrame({"a": [4, 5]})),
            (pl.DataFrame({"a": [1, 2, 3, 4]}), pl.DataFrame({"a": [5, 6]}))
        ]
        mock_wf_class.return_value = mock_wf_instance
        
        # Create the pipeline
        pipeline = ResearchPipeline(
            datalake=mock_datalake,
            feature_engine=mock_feature_engine,
            alpha_engine=mock_alpha_engine,
            regime_detector=mock_regime_detector,
            backtest_harness=mock_backtest_harness,
            model_registry=mock_model_registry,
            drift_monitor=mock_drift_monitor
        )
        
        # Run the pipeline
        result = await pipeline.run(
            symbols=["AAPL"],
            timeframe="1d",
            start_date="2023-01-01",
            end_date="2023-01-10",
            strategy_name="momentum",
            walk_forward=True,
            target_sharpe=0.5
        )
        
        # Verify the result
        assert isinstance(result, ResearchResult)
        assert result.strategy_name == "momentum"
        assert result.approved_for_deployment == True  # Should pass our thresholds
        assert result.config_path is not None
        assert result.tearsheet.sharpe_ratio == 0.67
        assert len(result.drift_report) == 2
        assert len(result.ic_report) > 0
        
        print("✓ ResearchPipeline test passed")
        return result


def test_deployment_bridge():
    """Test DeploymentBridge."""
    print("Testing DeploymentBridge...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "bot_paper.yaml"
        
        # Create a mock ResearchResult
        mock_tearsheet = TearsheetMetrics(
            total_return=0.15,
            ann_return=0.12,
            ann_volatility=0.18,
            sharpe_ratio=0.67,
            sortino_ratio=0.8,
            calmar_ratio=0.5,
            omega_ratio=1.2,
            max_drawdown=0.08,
            max_dd_duration_days=10,
            avg_dd_duration_days=5.0,
            recovery_time_days=15.0,
            total_trades=10,
            win_rate=0.6,
            avg_win_pct=0.02,
            avg_loss_pct=0.015,
            profit_factor=1.33,
            expected_value=0.005,
            avg_turnover_daily=0.1,
            total_cost_pct=0.02,
            skewness=0.1,
            kurtosis=0.2
        )
        
        mock_result = ResearchResult(
            strategy_name="momentum",
            tearsheet=mock_tearsheet,
            backtest_df=pl.DataFrame(),
            drift_report={"rsi": 0.05},
            approved_for_deployment=True,
            config_path=str(config_path),
            ic_report={"momentum_alpha": 0.3},
            regime_stats=pl.DataFrame({"regime_id": [0, 1], "sharpe": [0.5, 0.8]})
        )
        
        # Test the deployment bridge
        bridge = DeploymentBridge(config_path=config_path)
        returned_path = bridge.deploy(mock_result)
        
        # Verify the config file was created
        assert Path(returned_path).exists()
        assert returned_path == str(config_path)
        
        # Verify it contains expected content
        config_content = config_path.read_text()
        assert "strategy: momentum" in config_content
        assert "initial_capital: 100000.0" in config_content
        assert "signal_col: ml_signal" in config_content
        
        print("✓ DeploymentBridge test passed")


def test_backtest_harness():
    """Test BacktestHarness with mocked dependencies."""
    print("Testing BacktestHarness...")
    
    # Create mock dependencies
    mock_engine = MagicMock(spec=VectorizedEngine)
    mock_tearsheet_gen = MagicMock(spec=TearsheetGenerator)
    mock_broker = MagicMock()
    
    # Set up mock return values
    mock_engine.backtest.return_value = {
        "equity_curve": pl.DataFrame({
            "timestamp": pl.date_range("2023-01-01", periods=5, interval="1d"),
            "equity": [100000.0, 101000.0, 102000.0, 101500.0, 103000.0]
        }),
        "trades": pl.DataFrame(),
        "full_df": pl.DataFrame({
            "timestamp": pl.date_range("2023-01-01", periods=5, interval="1d"),
            "symbol": ["AAPL"] * 5,
            "close": [100.0, 101.0, 102.0, 101.5, 103.0],
            "signal": [0.1, -0.1, 0.2, -0.2, 0.1]
        })
    }
    
    mock_tearsheet = TearsheetMetrics(
        total_return=0.03,
        ann_return=0.12,
        ann_volatility=0.15,
        sharpe_ratio=0.8,
        sortino_ratio=1.0,
        calmar_ratio=0.6,
        omega_ratio=1.3,
        max_drawdown=0.02,
        max_dd_duration_days=5,
        avg_dd_duration_days=2.5,
        recovery_time_days=7.0,
        total_trades=5,
        win_rate=0.6,
        avg_win_pct=0.015,
        avg_loss_pct=0.01,
        profit_factor=1.5,
        expected_value=0.008,
        avg_turnover_daily=0.2,
        total_cost_pct=0.01,
        skewness=0.0,
        kurtosis=0.1
    )
    mock_tearsheet_gen.generate.return_value = mock_tearsheet
    mock_tearsheet_gen.to_html.return_value = "/tmp/test_report.html"
    
    # Create the harness
    harness = BacktestHarness(
        engine=mock_engine,
        tearsheet_gen=mock_tearsheet_gen,
        broker=mock_broker
    )
    
    # Run a backtest
    test_df = pl.DataFrame({
        "timestamp": pl.date_range("2023-01-01", periods=5, interval="1d"),
        "symbol": ["AAPL"] * 5,
        "close": [100.0, 101.0, 102.0, 101.5, 103.0],
        "signal": [0.1, -0.1, 0.2, -0.2, 0.1],
        "volume": [1000.0] * 5
    })
    
    result = harness.run(
        df=test_df,
        signal_col="signal",
        strategy_name="test_strategy"
    )
    
    # Verify the result
    assert isinstance(result, BacktestResult)
    assert result.strategy_name == "test_strategy"
    assert result.tearsheet.sharpe_ratio == 0.8
    assert result.html_report_path == "/tmp/test_report.html"
    assert result.backtest_df.height == 5
    
    print("✓ BacktestHarness test passed")


async def main():
    """Run all integration tests."""
    print("Running QTrader Pipeline Integration Tests\n")
    
    try:
        # Test ResearchPipeline
        research_result = await test_research_pipeline_with_mocks()
        
        # Test DeploymentBridge
        test_deployment_bridge()
        
        # Test BacktestHarness
        test_backtest_harness()
        
        print("\n✅ All integration tests passed!")
        print("\nSummary:")
        print("- ResearchPipeline: ✓")
        print("- DeploymentBridge: ✓")
        print("- BacktestHarness: ✓")
        print("\nThe pipeline components are working correctly together.")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)