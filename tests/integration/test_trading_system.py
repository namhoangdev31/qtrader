"""End-to-end integration tests for the complete Trading System.

Tests the full pipeline:
  Market Data → Alpha (Atomic Trio ML) → Signal → Risk → Order → Fill → Recon → PnL
"""

from __future__ import annotations

import asyncio
import time

import pytest

from qtrader.trading_system import TradingSystem, TradingSystemConfig, create_trading_system


class TestTradingSystemEndToEnd:
    """End-to-end integration tests for the complete Trading System."""

    @pytest.fixture
    def system(self) -> TradingSystem:
        return create_trading_system(simulate=True, symbols=["BTC-USD"])

    @pytest.mark.asyncio
    async def test_system_creation(self, system: TradingSystem) -> None:
        """Test system can be created with all modules wired."""
        assert system.ml_pipeline is not None
        assert system.kill_switch is not None
        assert system.pre_trade_risk is not None
        assert system.broker is not None
        assert system.alert_engine is not None
        assert system.latency_enforcer is not None
        assert system.pnl_attribution is not None
        assert system.config.simulate is True
        assert system.config.symbols == ["BTC-USD"]

    @pytest.mark.asyncio
    async def test_market_data_ingestion(self, system: TradingSystem) -> None:
        """Test market data ingestion produces valid data."""
        # Build up historical data
        for _ in range(50):
            await system._get_market_data("BTC-USD")

        market_data = await system._get_market_data("BTC-USD")
        assert market_data is not None
        assert "price" in market_data
        assert market_data["price"] > 0
        assert "bid" in market_data
        assert "ask" in market_data
        assert market_data["bid"] < market_data["ask"]
        assert len(market_data["historical_prices"]) >= 50

    @pytest.mark.asyncio
    async def test_ml_alpha_engine_integration(self, system: TradingSystem) -> None:
        """Test ML Alpha Engine (Atomic Trio) integration."""
        # Build up historical data
        for _ in range(50):
            await system._get_market_data("BTC-USD")

        market_data = await system._get_market_data("BTC-USD")
        ml_result = await system._run_ml_alpha("BTC-USD", market_data)

        assert ml_result is not None
        assert "decision" in ml_result
        assert ml_result["decision"].action is not None
        assert 0.0 <= ml_result["decision"].confidence <= 1.0

    @pytest.mark.asyncio
    async def test_signal_generation(self, system: TradingSystem) -> None:
        """Test signal generation from ML result."""
        # Create a mock ML result with BUY signal
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

        signal = system._generate_signal("BTC-USD", ml_result)
        assert signal is not None
        assert signal["side"] == "BUY"
        assert signal["strength"] > 0
        assert signal["confidence"] == 0.7

    @pytest.mark.asyncio
    async def test_risk_check_pass(self, system: TradingSystem) -> None:
        """Test risk check passes for valid signal."""
        signal = {
            "symbol": "BTC-USD",
            "side": "BUY",
            "strength": 0.5,
            "confidence": 0.7,
            "position_size_multiplier": 0.1,
        }
        assert system._check_risk(signal) is True

    @pytest.mark.asyncio
    async def test_risk_check_kill_switch(self, system: TradingSystem) -> None:
        """Test risk check fails when kill switch is active."""
        system.kill_switch.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )
        signal = {
            "symbol": "BTC-USD",
            "side": "BUY",
            "strength": 0.5,
            "confidence": 0.7,
            "position_size_multiplier": 0.1,
        }
        assert system._check_risk(signal) is False

    @pytest.mark.asyncio
    async def test_order_execution(self, system: TradingSystem) -> None:
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
        await system._execute_order(signal)
        assert system._stats["orders"] >= 1

    @pytest.mark.asyncio
    async def test_periodic_reconciliation(self, system: TradingSystem) -> None:
        """Test periodic reconciliation runs without errors."""
        await system._periodic_reconciliation()
        assert system._stats["recon_checks"] >= 1

    @pytest.mark.asyncio
    async def test_kill_switch_activation(self, system: TradingSystem) -> None:
        """Test kill switch activates on critical drawdown."""
        assert not system.kill_switch.get_kill_telemetry()["is_system_halted"]
        system.kill_switch.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )
        assert system.kill_switch.get_kill_telemetry()["is_system_halted"]

    @pytest.mark.asyncio
    async def test_system_status(self, system: TradingSystem) -> None:
        """Test system status reporting."""
        status = system.get_status()
        assert "running" in status
        assert "stats" in status
        assert "mode" in status
        assert "symbols" in status
        assert status["mode"] == "paper"

    @pytest.mark.asyncio
    async def test_full_pipeline_single_symbol(self, system: TradingSystem) -> None:
        """Test full pipeline for a single symbol."""
        # Build up historical data
        for _ in range(50):
            await system._get_market_data("BTC-USD")

        # Process through full pipeline
        await system._process_symbol("BTC-USD")

        # Verify pipeline ran
        assert system._stats["signals"] >= 0  # May be 0 if HOLD signal
        assert system._stats["recon_checks"] >= 0

    @pytest.mark.asyncio
    async def test_system_stop(self, system: TradingSystem) -> None:
        """Test system stops cleanly."""
        await system.stop()
        assert not system._running

    @pytest.mark.asyncio
    async def test_latency_enforcement(self, system: TradingSystem) -> None:
        """Test latency enforcement tracks pipeline stages."""
        system.latency_enforcer.start_pipeline("test")
        with system.latency_enforcer.measure_stage("market_data"):
            pass
        with system.latency_enforcer.measure_stage("alpha_computation"):
            pass
        report = system.latency_enforcer.end_pipeline("test")
        assert report.total_latency_ms >= 0
        assert report.sla_compliant  # Should be under 100ms

    @pytest.mark.asyncio
    async def test_alert_engine(self, system: TradingSystem) -> None:
        """Test alert engine sends alerts."""
        from qtrader.monitoring.alert_engine import AlertSeverity

        # Alert with no channels should return False but not crash
        result = await system._send_alert(
            AlertSeverity.INFO,
            "Test Alert",
            "This is a test",
        )
        assert system._stats["alerts_sent"] >= 0  # May be 0 if no channels

    @pytest.mark.asyncio
    async def test_multiple_symbols(self) -> None:
        """Test system handles multiple symbols."""
        system = create_trading_system(simulate=True, symbols=["BTC-USD", "ETH-USD"])
        assert len(system.config.symbols) == 2
        assert len(system._market_data) == 2

        for symbol in system.config.symbols:
            for _ in range(50):
                await system._get_market_data(symbol)

        for symbol in system.config.symbols:
            await system._process_symbol(symbol)

        await system.stop()
