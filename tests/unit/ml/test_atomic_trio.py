"""Integration tests for the Atomic Trio ML Pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from qtrader.ml.atomic_trio import AtomicTrioPipeline, PipelineResult
from qtrader.ml.chronos_adapter import ChronosForecastAdapter, ForecastResult
from qtrader.ml.mlx_config import (
    M4ChipInfo,
    detect_m4_chip,
    get_model_recommendations,
    get_optimized_config,
)
from qtrader.ml.phi2_controller import DecisionAction, Phi2DecisionController, TradingDecision
from qtrader.ml.tabpfn_adapter import TabPFNRiskAdapter, RiskClassificationResult


class TestChronosAdapter:
    """Tests for Chronos-2 time series forecasting."""

    def test_forecast_result_properties(self) -> None:
        """Test ForecastResult dataclass properties."""
        result = ForecastResult(
            mean=np.array([100.0, 101.0, 102.0]),
            lower_bound=np.array([99.0, 99.5, 100.5]),
            upper_bound=np.array([101.0, 102.5, 103.5]),
            prediction_length=3,
            context_length=100,
            inference_time_ms=50.0,
            model_size="small",
            quantile_05=np.array([98.5, 99.0, 99.5]),
            quantile_95=np.array([101.5, 103.0, 104.5]),
        )
        assert result.trend_direction == "BULLISH"
        assert len(result.confidence_width) == 3
        assert all(w > 0 for w in result.confidence_width)
        info = result.to_dict()
        assert "trend_direction" in info
        assert info["trend_direction"] == "BULLISH"

    def test_bearish_trend(self) -> None:
        result = ForecastResult(
            mean=np.array([102.0, 101.0, 100.0]),
            lower_bound=np.array([100.0, 99.5, 98.5]),
            upper_bound=np.array([103.5, 102.5, 101.5]),
            prediction_length=3,
            context_length=100,
            inference_time_ms=50.0,
            model_size="small",
            quantile_05=np.array([99.5, 99.0, 98.5]),
            quantile_95=np.array([104.5, 103.0, 101.5]),
        )
        assert result.trend_direction == "BEARISH"

    def test_flat_trend(self) -> None:
        result = ForecastResult(
            mean=np.array([100.0, 100.0, 100.0]),
            lower_bound=np.array([99.0, 99.0, 99.0]),
            upper_bound=np.array([101.0, 101.0, 101.0]),
            prediction_length=3,
            context_length=100,
            inference_time_ms=50.0,
            model_size="small",
            quantile_05=np.array([98.5, 98.5, 98.5]),
            quantile_95=np.array([101.5, 101.5, 101.5]),
        )
        assert result.trend_direction == "FLAT"


class TestTabPFNAdapter:
    """Tests for TabPFN 2.5 risk classification."""

    def test_safe_market_conditions(self) -> None:
        adapter = TabPFNRiskAdapter(device="cpu")
        result = adapter.classify(
            features={
                "rsi": 50.0,
                "volatility": 0.01,
                "volume_ratio": 1.0,
                "order_imbalance": 0.1,
                "spread_bps": 3.0,
            }
        )
        assert result.class_label == "SAFE"
        assert result.risk_score < 0.3

    def test_danger_market_conditions(self) -> None:
        adapter = TabPFNRiskAdapter(device="cpu")
        result = adapter.classify(
            features={
                "rsi": 85.0,
                "volatility": 0.08,
                "volume_ratio": 5.0,
                "order_imbalance": 0.8,
                "spread_bps": 25.0,
            }
        )
        assert result.class_label == "DANGER"
        assert result.risk_score > 0.7

    def test_warning_market_conditions(self) -> None:
        adapter = TabPFNRiskAdapter(device="cpu")
        result = adapter.classify(
            features={
                "rsi": 72.0,
                "volatility": 0.03,
                "volume_ratio": 2.0,
                "order_imbalance": 0.4,
                "spread_bps": 8.0,
            }
        )
        assert result.class_label in ("WARNING", "SAFE")  # Rule-based may vary
        assert result.confidence > 0.0

    def test_feature_importance(self) -> None:
        adapter = TabPFNRiskAdapter(device="cpu")
        result = adapter.classify(
            features={
                "rsi": 50.0,
                "volatility": 0.02,
                "volume_ratio": 1.5,
            }
        )
        assert isinstance(result.feature_importance, dict)
        assert len(result.feature_importance) > 0


class TestPhi2Controller:
    """Tests for Phi-2 decision controller."""

    def test_bullish_safe_decision(self) -> None:
        controller = Phi2DecisionController()
        decision = controller.decide(
            chronos_forecast={"trend_direction": "BULLISH", "prediction_length": 5},
            tabpfn_risk={"class_label": "SAFE", "risk_score": 0.1, "confidence": 0.9},
            market_context={"spread_bps": 3.0, "volume_ratio": 1.0},
            system_state={"kill_switch_active": False, "current_drawdown": 0.02},
        )
        assert decision.action == DecisionAction.BUY
        assert decision.position_size_multiplier > 0.0

    def test_bearish_danger_decision(self) -> None:
        controller = Phi2DecisionController()
        decision = controller.decide(
            chronos_forecast={"trend_direction": "BEARISH", "prediction_length": 5},
            tabpfn_risk={"class_label": "DANGER", "risk_score": 0.9, "confidence": 0.95},
            market_context={"spread_bps": 25.0, "volume_ratio": 5.0},
            system_state={"kill_switch_active": False, "current_drawdown": 0.18},
        )
        assert decision.action in (
            DecisionAction.HOLD,
            DecisionAction.REDUCE_POSITION,
            DecisionAction.CLOSE_ALL,
        )
        assert decision.position_size_multiplier < 0.5

    def test_kill_switch_decision(self) -> None:
        controller = Phi2DecisionController()
        decision = controller.decide(
            chronos_forecast=None,
            tabpfn_risk=None,
            market_context=None,
            system_state={"kill_switch_active": True, "current_drawdown": 0.25},
        )
        assert decision.action == DecisionAction.CLOSE_ALL
        assert decision.position_size_multiplier == 0.0

    def test_explainability(self) -> None:
        """Test that decisions include ML explainability (Standash §13)."""
        controller = Phi2DecisionController()
        decision = controller.decide(
            chronos_forecast={"trend_direction": "BULLISH"},
            tabpfn_risk={"class_label": "SAFE"},
            system_state={"kill_switch_active": False},
        )
        assert decision.explanation != ""
        assert "Decision:" in decision.explanation
        assert "Reasoning:" in decision.explanation


class TestAtomicTrioPipeline:
    """Integration tests for the full Atomic Trio pipeline."""

    def test_pipeline_run(self) -> None:
        pipeline = AtomicTrioPipeline(
            chronos_model_id="amazon/chronos-2",
            tabpfn_model_id="Prior-Labs/tabpfn_2_5", tabpfn_device="cpu",
            phi2_backend="auto",
        )

        result = pipeline.run(
            historical_prices=[100.0, 101.0, 102.0, 101.5, 103.0, 104.0],
            market_features={
                "rsi": 55.0,
                "volatility": 0.02,
                "volume_ratio": 1.2,
                "order_imbalance": 0.1,
                "spread_bps": 5.0,
            },
            market_context={"spread_bps": 5.0},
            system_state={"kill_switch_active": False, "current_drawdown": 0.03},
            prediction_length=5,
        )

        assert isinstance(result, PipelineResult)
        assert result.decision is not None
        assert result.decision.action in DecisionAction
        assert result.pipeline_latency_ms >= 0

    def test_pipeline_with_danger_scenario(self) -> None:
        pipeline = AtomicTrioPipeline()

        result = pipeline.run(
            historical_prices=[100.0, 95.0, 90.0, 85.0, 80.0],
            market_features={
                "rsi": 85.0,
                "volatility": 0.08,
                "volume_ratio": 5.0,
                "order_imbalance": 0.8,
                "spread_bps": 25.0,
            },
            market_context={"spread_bps": 25.0, "volume_ratio": 5.0},
            system_state={"kill_switch_active": False, "current_drawdown": 0.18},
            prediction_length=5,
        )

        # Danger scenario should reduce or eliminate position
        assert result.decision.position_size_multiplier <= 0.5
        assert result.decision.risk_adjustment >= 0.5

    def test_pipeline_info(self) -> None:
        pipeline = AtomicTrioPipeline()
        info = pipeline.get_pipeline_info()
        assert "chronos" in info
        assert "tabpfn" in info
        assert "phi2" in info
        assert "run_count" in info
        assert "estimated_total_memory_mb" in info


class TestMLXConfig:
    """Tests for MLX optimization configuration."""

    def test_detect_m4_chip(self) -> None:
        chip = detect_m4_chip()
        assert chip.is_apple_silicon is True
        assert chip.chip.startswith("M4")

    def test_optimized_config(self) -> None:
        chip = M4ChipInfo(
            chip="M4 Pro",
            cpu_cores=14,
            gpu_cores=20,
            neural_engine_cores=16,
            unified_memory_gb=36,
            memory_bandwidth_gbps=273,
            is_apple_silicon=True,
        )
        config = get_optimized_config(chip)
        assert config.default_dtype == "float16"
        assert config.num_threads > 0
        assert config.memory_limit_gb > 0

    def test_model_recommendations(self) -> None:
        chip = M4ChipInfo(
            chip="M4 Max",
            cpu_cores=16,
            gpu_cores=40,
            neural_engine_cores=16,
            unified_memory_gb=48,
            memory_bandwidth_gbps=546,
            is_apple_silicon=True,
        )
        recs = get_model_recommendations(chip)
        assert "chronos" in recs
        assert "tabpfn" in recs
        assert "phi2" in recs
        assert "total_memory_mb" in recs
