"""
Level 2 Critical Tests: ML Model Management
Covers: MLflowManager (model registry, promotion, rollback, stale-model prevention),
FactorEngine (batch compute, multi-symbol, compute_latest).
Focus: Garbage-in/garbage-out prevention, model staleness, correctness of promotion gates.
"""
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import polars as pl
import pytest

# ===========================================================================
# MLflowManager
# ===========================================================================

@pytest.fixture
def manager_disabled():
    """MLflowManager with mlflow disabled — must not crash any public API."""
    from qtrader.ml.mlflow_manager import MLflowManager
    return MLflowManager(enable_mlflow=False)


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def manager_mocked(mock_client):
    """MLflowManager with real mlflow disabled but _client injected as mock."""
    from qtrader.ml.mlflow_manager import MLflowManager
    with patch("qtrader.ml.mlflow_manager.MLFLOW_AVAILABLE", False):
        mgr = MLflowManager(enable_mlflow=False)
    # Manually inject mocked client and re-enable for targeted tests
    mgr._client = mock_client
    mgr.enable_mlflow = True
    mgr._experiment_id = "exp_123"
    return mgr


# ---------------------------------------------------------------------------
# Disabled mode — must not crash
# ---------------------------------------------------------------------------

def test_manager_disabled_is_not_enabled(manager_disabled):
    assert manager_disabled.is_enabled() is False


@pytest.mark.asyncio
async def test_log_run_returns_none_when_disabled(manager_disabled):
    result = await manager_disabled.log_run("strat", {}, {})
    assert result is None


@pytest.mark.asyncio
async def test_evaluate_and_promote_returns_false_when_disabled(manager_disabled):
    result = await manager_disabled.evaluate_and_promote("strat", "run_id")
    assert result is False


@pytest.mark.asyncio
async def test_rollback_returns_false_when_disabled(manager_disabled):
    result = await manager_disabled.rollback_to_previous_production("strat")
    assert result is False


@pytest.mark.asyncio
async def test_load_production_model_returns_none_when_disabled(manager_disabled):
    result = await manager_disabled.load_production_model("strat")
    assert result is None


def test_get_model_status_returns_error_when_disabled(manager_disabled):
    status = manager_disabled.get_model_status("strat")
    assert "error" in status


# ---------------------------------------------------------------------------
# Promotion gate — must respect thresholds exactly
# ---------------------------------------------------------------------------

def test_promotion_gate_passes_all_criteria(manager_mocked, mock_client):
    """Model meeting all thresholds should be promoted to Production."""
    run = MagicMock()
    run.data.metrics = {"sharpe_ratio": 1.5, "max_drawdown": 0.05, "hit_rate": 0.52}
    mock_client.get_run.return_value = run

    staging_version = MagicMock()
    staging_version.version = "2"
    mock_client.get_latest_versions.return_value = [staging_version]

    result = manager_mocked._evaluate_and_promote_sync(
        "TestStrat", "run_abc", sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5
    )
    assert result is True
    mock_client.transition_model_version_stage.assert_called_once_with(
        name="strategy_TestStrat", version="2", stage="Production", archive_existing_versions=True
    )


def test_promotion_gate_fails_on_sharpe(manager_mocked, mock_client):
    run = MagicMock()
    run.data.metrics = {"sharpe_ratio": 0.5, "max_drawdown": 0.04, "hit_rate": 0.55}
    mock_client.get_run.return_value = run
    result = manager_mocked._evaluate_and_promote_sync(
        "TestStrat", "run_bad", sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5
    )
    assert result is False
    mock_client.transition_model_version_stage.assert_not_called()


def test_promotion_gate_fails_on_drawdown(manager_mocked, mock_client):
    run = MagicMock()
    run.data.metrics = {"sharpe_ratio": 2.0, "max_drawdown": 0.25, "hit_rate": 0.60}
    mock_client.get_run.return_value = run
    result = manager_mocked._evaluate_and_promote_sync(
        "TestStrat", "run_bad_dd", sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5
    )
    assert result is False


def test_promotion_gate_fails_on_hit_rate(manager_mocked, mock_client):
    run = MagicMock()
    run.data.metrics = {"sharpe_ratio": 2.0, "max_drawdown": 0.05, "hit_rate": 0.45}
    mock_client.get_run.return_value = run
    result = manager_mocked._evaluate_and_promote_sync(
        "TestStrat", "run_lowhr", sharpe_threshold=1.0, drawdown_threshold=0.1, hit_rate_threshold=0.5
    )
    assert result is False


def test_promotion_gate_no_staging_version_returns_false(manager_mocked, mock_client):
    run = MagicMock()
    run.data.metrics = {"sharpe_ratio": 2.0, "max_drawdown": 0.03, "hit_rate": 0.7}
    mock_client.get_run.return_value = run
    mock_client.get_latest_versions.return_value = []   # No staging version

    result = manager_mocked._evaluate_and_promote_sync(
        "NoStaging", "run_id", 1.0, 0.1, 0.5
    )
    assert result is False


# ---------------------------------------------------------------------------
# Rollback — must restore previous production
# ---------------------------------------------------------------------------

def test_rollback_archives_current_and_restores_previous(manager_mocked, mock_client):
    prod_v = MagicMock(); prod_v.version = "5"
    arch_v3 = MagicMock(); arch_v3.version = "3"
    arch_v4 = MagicMock(); arch_v4.version = "4"

    mock_client.get_latest_versions.side_effect = [
        [prod_v],            # Production query
        [arch_v3, arch_v4],  # Archived query
    ]
    result = manager_mocked._rollback_to_previous_production_sync("Strat")

    assert result is True
    calls = mock_client.transition_model_version_stage.call_args_list
    # First call: archive current production (v5)
    assert calls[0].kwargs["version"] == "5"
    assert calls[0].kwargs["stage"] == "Archived"
    # Second call: restore highest archived version (v4)
    assert calls[1].kwargs["version"] == "4"
    assert calls[1].kwargs["stage"] == "Production"


def test_rollback_no_production_returns_false(manager_mocked, mock_client):
    mock_client.get_latest_versions.return_value = []
    assert manager_mocked._rollback_to_previous_production_sync("Strat") is False


def test_rollback_no_archived_returns_false(manager_mocked, mock_client):
    prod_v = MagicMock(); prod_v.version = "2"
    mock_client.get_latest_versions.side_effect = [[prod_v], []]
    assert manager_mocked._rollback_to_previous_production_sync("Strat") is False


# ---------------------------------------------------------------------------
# Load production model — stale model prevention
# ---------------------------------------------------------------------------

def test_load_production_model_returns_uri(manager_mocked, mock_client):
    v = MagicMock(); v.version = "3"
    mock_client.get_latest_versions.return_value = [v]
    uri = manager_mocked._load_production_model_sync("MyStrat")
    assert uri == "models:/strategy_MyStrat/3"


def test_load_production_model_none_when_no_version(manager_mocked, mock_client):
    mock_client.get_latest_versions.return_value = []
    assert manager_mocked._load_production_model_sync("Ghost") is None


# ===========================================================================
# FactorEngine
# ===========================================================================

from qtrader.features.base import BaseFeature


class DoubleFeature(BaseFeature):
    name = "double_close"
    version = "1.0"
    required_cols = ["close"]
    min_periods = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return (df["close"] * 2).rename(self.name)


class SumFeature(BaseFeature):
    name = "hl_sum"
    version = "1.0"
    required_cols = ["high", "low"]
    min_periods = 1

    def compute(self, df: pl.DataFrame) -> pl.Series:
        return (df["high"] + df["low"]).rename(self.name)


def make_engine():
    from qtrader.features.engine import FactorEngine
    store = MagicMock()
    return FactorEngine(store=store), store


def test_factor_engine_register_and_list_names():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    engine.register_factor(SumFeature())
    names = engine.get_all_feature_names()
    assert "double_close" in names
    assert "hl_sum" in names


def test_factor_engine_compute_no_factors_returns_empty():
    engine, _ = make_engine()
    df = pl.DataFrame({"close": [100.0, 110.0]})
    result = engine.compute(df)
    assert result.is_empty()


def test_factor_engine_compute_single_factor():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    df = pl.DataFrame({"close": [50.0, 60.0, 70.0]})
    result = engine.compute(df)
    assert "double_close" in result.columns
    assert result["double_close"].to_list() == [100.0, 120.0, 140.0]


def test_factor_engine_compute_multiple_factors():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    engine.register_factor(SumFeature())
    df = pl.DataFrame({"close": [100.0], "high": [105.0], "low": [95.0]})
    result = engine.compute(df)
    assert "double_close" in result.columns
    assert "hl_sum" in result.columns
    assert result["double_close"][0] == 200.0
    assert result["hl_sum"][0] == 200.0


def test_factor_engine_compute_latest_returns_one_row():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    df = pl.DataFrame({"close": [100.0, 110.0, 120.0]})
    latest = engine.compute_latest(df)
    assert latest.height == 1
    assert latest["double_close"][0] == 240.0


def test_factor_engine_compute_and_save_calls_store(tmp_path):
    engine, store = make_engine()
    engine.register_factor(DoubleFeature())
    df = pl.DataFrame({"close": [100.0, 110.0]})
    engine.compute_and_save(df, "BTC", "1d")
    store.save_features.assert_called_once()


def test_factor_engine_multi_symbol_adds_symbol_column():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    raw = {
        "BTC": pl.DataFrame({"close": [50000.0]}),
        "ETH": pl.DataFrame({"close": [3000.0]}),
    }
    result = engine.compute_multi_symbol(raw, "1h")
    assert "symbol" in result.columns
    symbols = result["symbol"].to_list()
    assert "BTC" in symbols
    assert "ETH" in symbols


def test_factor_engine_output_row_count_matches_input():
    engine, _ = make_engine()
    engine.register_factor(DoubleFeature())
    df = pl.DataFrame({"close": [float(i) for i in range(100)]})
    result = engine.compute(df)
    assert result.height == 100
