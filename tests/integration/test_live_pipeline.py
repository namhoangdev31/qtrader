"""Integration tests for the live trading pipeline."""

from __future__ import annotations

import asyncio

import pytest

from qtrader.live_pipeline import LiveTradingPipeline, PipelineConfig, create_pipeline


class TestLiveTradingPipeline:
    """Integration tests for the end-to-end live trading pipeline."""

    @pytest.fixture
    def pipeline(self) -> LiveTradingPipeline:
        return create_pipeline(simulate=True, symbols=["BTC-USD"])

    @pytest.mark.asyncio
    async def test_pipeline_creation(self, pipeline: LiveTradingPipeline) -> None:
        """Test pipeline can be created with default config."""
        assert pipeline.config.simulate is True
        assert pipeline.config.symbols == ["BTC-USD"]
        assert pipeline.ml_pipeline is not None
        assert pipeline.kill_switch is not None
        assert pipeline.pre_trade_risk is not None
        assert pipeline.broker is not None

    @pytest.mark.asyncio
    async def test_market_data_generation(self, pipeline: LiveTradingPipeline) -> None:
        """Test market data generation produces valid data."""
        # Build up historical data
        for _ in range(50):
            await pipeline._get_market_data("BTC-USD")

        market_data = await pipeline._get_market_data("BTC-USD")
        assert market_data is not None
        assert "price" in market_data
        assert market_data["price"] > 0
        assert len(market_data["historical_prices"]) >= 50

    @pytest.mark.asyncio
    async def test_ml_alpha_engine(self, pipeline: LiveTradingPipeline) -> None:
        """Test ML Alpha Engine produces valid results."""
        # Build up historical data
        for _ in range(50):
            await pipeline._get_market_data("BTC-USD")

        market_data = await pipeline._get_market_data("BTC-USD")
        ml_result = await pipeline._run_ml_alpha("BTC-USD", market_data)

        assert ml_result is not None
        assert "decision" in ml_result
        assert ml_result["decision"].action is not None
        assert 0.0 <= ml_result["decision"].confidence <= 1.0

    @pytest.mark.asyncio
    async def test_signal_generation(self, pipeline: LiveTradingPipeline) -> None:
        """Test signal generation from ML results."""
        ml_result = {
            "decision": type(
                "Decision",
                (),
                {
                    "action": type("Action", (), {"value": "BUY"})(),
                    "confidence": 0.7,
                    "position_size_multiplier": 0.5,
                    "stop_loss_pct": 2.0,
                    "take_profit_pct": 5.0,
                    "reasoning": "Test signal",
                    "explanation": "Test explanation",
                },
            )(),
            "chronos_forecast": {"trend_direction": "BULLISH"},
            "tabpfn_risk": {"class_label": "SAFE"},
        }

        signal = pipeline._generate_signal("BTC-USD", ml_result)
        assert signal is not None
        assert signal["side"] == "BUY"
        assert signal["strength"] > 0
        assert signal["confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_hold_signal(self, pipeline: LiveTradingPipeline) -> None:
        """Test that HOLD action produces no signal."""
        ml_result = {
            "decision": type(
                "Decision",
                (),
                {
                    "action": type("Action", (), {"value": "HOLD"})(),
                    "confidence": 0.5,
                    "position_size_multiplier": 0.5,
                    "stop_loss_pct": 2.0,
                    "take_profit_pct": 5.0,
                    "reasoning": "No strong signal",
                    "explanation": "Hold explanation",
                },
            )(),
        }

        signal = pipeline._generate_signal("BTC-USD", ml_result)
        assert signal is None

    @pytest.mark.asyncio
    async def test_risk_check_pass(self, pipeline: LiveTradingPipeline) -> None:
        """Test risk check passes for valid signal."""
        signal = {
            "symbol": "BTC-USD",
            "side": "BUY",
            "strength": 0.5,
            "confidence": 0.7,
            "position_size_multiplier": 0.5,
        }

        assert pipeline._check_risk(signal) is True

    @pytest.mark.asyncio
    async def test_risk_check_kill_switch(self, pipeline: LiveTradingPipeline) -> None:
        """Test risk check fails when kill switch is active."""
        pipeline.kill_switch.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )

        signal = {
            "symbol": "BTC-USD",
            "side": "BUY",
            "strength": 0.5,
            "confidence": 0.7,
            "position_size_multiplier": 0.5,
        }

        assert pipeline._check_risk(signal) is False

    @pytest.mark.asyncio
    async def test_order_execution(self, pipeline: LiveTradingPipeline) -> None:
        """Test order execution through broker."""
        signal = {
            "symbol": "BTC-USD",
            "side": "BUY",
            "strength": 0.5,
            "confidence": 0.7,
            "position_size_multiplier": 0.1,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 5.0,
            "reasoning": "Test",
            "explanation": "Test explanation",
        }

        await pipeline._execute_order(signal)
        assert pipeline._order_count >= 1

    @pytest.mark.asyncio
    async def test_kill_switch_activation(self, pipeline: LiveTradingPipeline) -> None:
        """Test kill switch activates on critical drawdown."""
        assert not pipeline.kill_switch.get_kill_telemetry()["is_system_halted"]

        pipeline.kill_switch.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )

        assert pipeline.kill_switch.get_kill_telemetry()["is_system_halted"]

    @pytest.mark.asyncio
    async def test_pipeline_stop(self, pipeline: LiveTradingPipeline) -> None:
        """Test pipeline stops cleanly."""
        await pipeline.stop()
        assert not pipeline._running
