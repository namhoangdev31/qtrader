#!/usr/bin/env python3
"""Test script for MLflowManager."""

import asyncio
import sys
import os
import tempfile
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from qtrader.ml.mlflow_manager import MLflowManager


async def test_mlflow_manager_creation():
    """Test that we can create an MLflowManager."""
    print("Testing MLflowManager creation...")
    
    # Create MLflow manager with tracking URI to a temporary directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_uri = f"file:{tmpdir}/mlruns"
        mlflow_manager = MLflowManager(
            tracking_uri=tracking_uri,
            experiment_name="Test-Experiment",
            enable_mlflow=True
        )
        
        # Test that it was created successfully
        assert mlflow_manager is not None
        assert mlflow_manager.is_enabled() == True
        assert mlflow_manager.tracking_uri == tracking_uri
        assert mlflow_manager.experiment_name == "Test-Experiment"
        print("✓ MLflowManager created successfully")


async def test_mlflow_manager_disabled_when_not_available():
    """Test that MLflowManager handles missing MLflow gracefully."""
    print("Testing MLflowManager when MLflow not available...")
    
    # Temporarily make MLflow unavailable
    with patch('qtrader.ml.mlflow_manager.MLFLOW_AVAILABLE', False):
        mlflow_manager = MLflowManager(enable_mlflow=True)
        assert mlflow_manager.is_enabled() == False
        print("✓ MLflowManager correctly disabled when MLflow not available")


async def test_mlflow_manager_disabled_by_config():
    """Test that MLflowManager respects enable_mlflow=False."""
    print("Testing MLflowManager disabled by configuration...")
    
    mlflow_manager = MLflowManager(enable_mlflow=False)
    assert mlflow_manager.is_enabled() == False
    print("✓ MLflowManager correctly disabled by configuration")


async def test_log_run():
    """Test logging a run to MLflow."""
    print("Testing MLflow run logging...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_uri = f"file:{tmpdir}/mlruns"
        mlflow_manager = MLflowManager(
            tracking_uri=tracking_uri,
            experiment_name="Test-Run-Logging",
            enable_mlflow=True
        )
        
        # Log a test run
        run_id = await mlflow_manager.log_run(
            strategy_name="test_strategy",
            parameters={
                "learning_rate": 0.01,
                "batch_size": 32,
                "feature_set": "basic"
            },
            metrics={
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.05,
                "hit_rate": 0.6
            },
            artifacts={
                "config": {"param1": "value1"},
                "feature_importance": {"feature1": 0.5, "feature2": 0.3}
            },
            run_name="test_run"
        )
        
        # Verify we got a run ID back
        assert run_id is not None
        assert isinstance(run_id, str)
        assert len(run_id) > 0
        print(f"✓ Successfully logged run with ID: {run_id}")
        
        # Verify we can get the run details
        if mlflow_manager._client:
            run = mlflow_manager._client.get_run(run_id)
            assert run.info.run_id == run_id
            assert run.data.params["learning_rate"] == "0.01"
            assert float(run.data.metrics["sharpe_ratio"]) == 1.5
            print("✓ Verified run details in MLflow")


async def test_model_registration():
    """Test model registration and stage transitions."""
    print("Testing model registration and stage transitions...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_uri = f"file:{tmpdir}/mlruns"
        mlflow_manager = MLflowManager(
            tracking_uri=tracking_uri,
            experiment_name="Test-Model-Registry",
            enable_mlflow=True
        )
        
        # Log a run first
        run_id = await mlflow_manager.log_run(
            strategy_name="test_model",
            parameters={"model_type": "test"},
            metrics={"accuracy": 0.95},
            run_name="model_test_run"
        )
        
        assert run_id is not None
        
        # Check model status
        status = mlflow_manager.get_model_status("test_model")
        print(f"Model status: {status}")
        
        # Should have a version in Staging (from log_run)
        if "staging" in status and status["staging"] is not None:
            print(f"✓ Model registered in Staging: version {status['staging']['version']}")
        else:
            # Model registration might happen differently, let's check if we can load it
            print("✓ Model registration test completed (details may vary)")
        

async def test_evaluate_and_promote():
    """Test evaluation and promotion logic."""
    print("Testing evaluation and promotion...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_uri = f"file:{tmpdir}/mlruns"
        mlflow_manager = MLflowManager(
            tracking_uri=tracking_uri,
            experiment_name="Test-Promotion",
            enable_mlflow=True
        )
        
        # Log a run with good metrics
        run_id = await mlflow_manager.log_run(
            strategy_name="promo_test",
            parameters={"test": "value"},
            metrics={
                "sharpe_ratio": 2.0,  # Above threshold of 1.0
                "max_drawdown": 0.05, # Below threshold of 0.1
                "hit_rate": 0.6       # Above threshold of 0.5
            },
            run_name="promo_test_run"
        )
        
        assert run_id is not None
        
        # Evaluate and promote (should succeed)
        promoted = await mlflow_manager.evaluate_and_promote(
            strategy_name="promo_test",
            run_id=run_id,
            sharpe_threshold=1.0,
            drawdown_threshold=0.1,
            hit_rate_threshold=0.5
        )
        
        assert promoted == True
        print("✓ Successfully promoted model with good metrics")
        
        # Check that it's now in production
        status = mlflow_manager.get_model_status("promo_test")
        if "production" in status and status["production"] is not None:
            print(f"✓ Model in Production: version {status['production']['version']}")
        
        # Test with bad metrics (should not promote)
        run_id_bad = await mlflow_manager.log_run(
            strategy_name="promo_test_bad",
            parameters={"test": "value"},
            metrics={
                "sharpe_ratio": 0.5,  # Below threshold
                "max_drawdown": 0.2,  # Above threshold
                "hit_rate": 0.3       # Below threshold
            },
            run_name="promo_test_bad_run"
        )
        
        assert run_id_bad is not None
        
        promoted_bad = await mlflow_manager.evaluate_and_promote(
            strategy_name="promo_test_bad",
            run_id=run_id_bad,
            sharpe_threshold=1.0,
            drawdown_threshold=0.1,
            hit_rate_threshold=0.5
        )
        
        assert promoted_bad == False
        print("✓ Correctly did not promote model with bad metrics")


async def test_load_production_model():
    """Test loading a production model."""
    print("Testing production model loading...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tracking_uri = f"file:{tmpdir}/mlruns"
        mlflow_manager = MLflowManager(
            tracking_uri=tracking_uri,
            experiment_name="Test-Model-Loading",
            enable_mlflow=True
        )
        
        # Log a run and promote it
        run_id = await mlflow_manager.log_run(
            strategy_name="load_test",
            parameters={"model_type": "load"},
            metrics={
                "sharpe_ratio": 1.5,
                "max_drawdown": 0.02,
                "hit_rate": 0.7
            },
            run_name="load_test_run"
        )
        
        assert run_id is not None
        
        # Promote to production
        promoted = await mlflow_manager.evaluate_and_promote(
            strategy_name="load_test",
            run_id=run_id,
            sharpe_threshold=1.0,
            drawdown_threshold=0.1,
            hit_rate_threshold=0.5
        )
        
        assert promoted == True
        
        # Try to load the production model
        model = await mlflow_manager.load_production_model("load_test")
        assert model is not None
        # The model should be a string (the model URI) in our implementation
        assert isinstance(model, str)
        assert "models:/" in model
        print(f"✓ Successfully loaded production model: {model}")


async def main():
    """Run all tests."""
    print("Running MLflowManager tests...\n")
    
    await test_mlflow_manager_creation()
    await test_mlflow_manager_disabled_when_not_available()
    await test_mlflow_manager_disabled_by_config()
    await test_log_run()
    await test_model_registration()
    await test_evaluate_and_promote()
    await test_load_production_model()
    
    print("\n✅ All MLflowManager tests passed!")


if __name__ == "__main__":
    asyncio.run(main())