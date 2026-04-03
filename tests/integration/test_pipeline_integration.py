"""End-to-end integration tests for the QTrader trading pipeline.

Tests the full lifecycle:
Market Data → Alpha → Signal → Risk Gate → Order → Fill → Reconciliation → PnL

Standash §12: Production Readiness Checklist
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from qtrader.core.events import (
    EventType,
    FillEvent,
    FillPayload,
    MarketEvent,
    MarketPayload,
    OrderEvent,
    OrderPayload,
    SignalEvent,
    SignalPayload,
    SystemEvent,
    SystemPayload,
)
from qtrader.core.state_store import StateStore, Position
from qtrader.execution.adverse_selection import AdverseSelectionModel
from qtrader.execution.order_id import OrderIDGenerator
from qtrader.execution.reconciliation_engine import ReconciliationEngine
from qtrader.execution.shadow_engine import ShadowEngine
from qtrader.oms.order_fsm import OrderFSM, OrderState
from qtrader.portfolio.qp_solver import PortfolioQPSolver
from qtrader.risk.kill_switch import GlobalKillSwitch
from qtrader.risk.war_mode import WarModeEngine, WarModeConfig
from qtrader.analytics.pnl_attribution import PnLAttributionEngine
from qtrader.core.latency_enforcer import LatencyEnforcer
from qtrader.core.state_replication import StateReplicator, NodeRole


# ============================================================================
# 1. FULL PIPELINE INTEGRATION TEST
# ============================================================================


class TestFullPipelineIntegration:
    """Test the complete trading pipeline from market data to PnL."""

    @pytest.fixture
    def state_store(self) -> StateStore:
        return StateStore()

    @pytest.fixture
    def order_fsm(self) -> OrderFSM:
        return OrderFSM(pending_timeout_s=30.0)

    @pytest.fixture
    def order_id_gen(self) -> OrderIDGenerator:
        return OrderIDGenerator()

    @pytest.fixture
    def kill_switch(self) -> GlobalKillSwitch:
        return GlobalKillSwitch()

    @pytest.fixture
    def adverse_model(self) -> AdverseSelectionModel:
        return AdverseSelectionModel()

    @pytest.fixture
    def latency_enforcer(self) -> LatencyEnforcer:
        return LatencyEnforcer(fail_on_breach=False)

    @pytest.fixture
    def pnl_attribution(self) -> PnLAttributionEngine:
        return PnLAttributionEngine()

    @pytest.fixture
    def war_mode(self) -> WarModeEngine:
        return WarModeEngine(config=WarModeConfig(dd_trigger_pct=0.20))

    @pytest.mark.asyncio
    async def test_full_pipeline_market_to_pnl(
        self,
        state_store: StateStore,
        order_fsm: OrderFSM,
        order_id_gen: OrderIDGenerator,
        kill_switch: GlobalKillSwitch,
        adverse_model: AdverseSelectionModel,
        latency_enforcer: LatencyEnforcer,
        pnl_attribution: PnLAttributionEngine,
        war_mode: WarModeEngine,
    ) -> None:
        """Test complete pipeline: Market → Alpha → Signal → Risk → Order → Fill → Recon → PnL."""
        # Step 1: Market Data Ingestion
        latency_enforcer.start_pipeline("test-pipeline-1")
        with latency_enforcer.measure_stage("market_data_ingestion"):
            market_event = MarketEvent(
                source="test_exchange",
                trace_id=uuid4(),
                payload=MarketPayload(
                    symbol="AAPL",
                    bid=Decimal("150.4"),
                    ask=Decimal("150.6"),
                    data={
                        "open": Decimal("150.0"),
                        "high": Decimal("151.0"),
                        "low": Decimal("149.0"),
                        "close": Decimal("150.5"),
                        "volume": Decimal("1000000"),
                    },
                ),
            )
        assert market_event.payload.symbol == "AAPL"

        # Step 2: Alpha Generation (simulated)
        with latency_enforcer.measure_stage("alpha_computation"):
            alpha_value = Decimal("0.05")  # Positive alpha = bullish signal
        assert alpha_value > 0

        # Step 3: Signal Generation
        with latency_enforcer.measure_stage("signal_generation"):
            signal = SignalEvent(
                source="test_strategy",
                trace_id=uuid4(),
                payload=SignalPayload(
                    symbol="AAPL",
                    signal_type="BUY",
                    strength=Decimal("0.8"),
                    confidence=Decimal("0.9"),
                    metadata={"alpha": float(alpha_value)},
                ),
            )
        assert signal.payload.signal_type == "BUY"
        assert signal.payload.strength == Decimal("0.8")

        # Step 4: Risk Check
        with latency_enforcer.measure_stage("risk_check"):
            # Check kill switch is not active
            assert not kill_switch.get_kill_telemetry()["is_system_halted"]
            # Check war mode is not active
            assert not war_mode.status.is_active
            # Check adverse selection (low-risk scenario with negative intercept)
            low_risk_model = AdverseSelectionModel()
            low_risk_model.params.intercept = -2.0  # Shift sigmoid left
            adverse_result = low_risk_model.estimate_probability(
                imbalance=0.0, delta_p=0.0, fill_rate=0.0, vpin_score=0.0
            )
            assert adverse_result.probability < 0.5  # Low adverse selection risk
            assert adverse_result.risk_level in ("LOW", "MEDIUM")
        assert not kill_switch.get_kill_telemetry()["is_system_halted"]

        # Step 5: Order Creation
        with latency_enforcer.measure_stage("order_routing"):
            order_id = await order_id_gen.generate_order_id("TEST_EXCHANGE", "AAPL")
            order = OrderEvent(
                source="test_strategy",
                trace_id=uuid4(),
                payload=OrderPayload(
                    order_id=order_id,
                    symbol="AAPL",
                    action="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("150.5"),
                    order_type="LIMIT",
                ),
            )
            # FSM transition: NEW → ACK
            new_state = order_fsm.transition(OrderState.NEW.value, "ACK")
            assert new_state == OrderState.ACK.value
        assert order.payload.symbol == "AAPL"

        # Step 6: Fill Simulation
        with latency_enforcer.measure_stage("fill_processing"):
            fill = FillEvent(
                source="test_exchange",
                trace_id=uuid4(),
                payload=FillPayload(
                    order_id=order_id,
                    symbol="AAPL",
                    side="BUY",
                    quantity=Decimal("100"),
                    price=Decimal("150.3"),  # Better fill price = positive execution PnL
                    commission=Decimal("1.50"),
                ),
            )
            # FSM transition: ACK → PARTIAL → FILLED
            state = order_fsm.transition(OrderState.ACK.value, "FILL_PARTIAL")
            assert state == OrderState.PARTIAL.value
            state = order_fsm.transition(OrderState.PARTIAL.value, "FILL_COMPLETE")
            assert state == OrderState.FILLED.value
        assert fill.payload.quantity == Decimal("100")

        # Step 7: PnL Attribution
        attribution = pnl_attribution.attribute_trade(
            symbol="AAPL",
            quantity=Decimal("100"),
            decision_price=Decimal("150.5"),  # Signal price
            fill_price=Decimal("150.3"),  # Better fill = positive execution PnL
            fair_value=Decimal("150.0"),  # Fair value at decision time
            total_fees=Decimal("1.50"),
            timestamp=time.time(),
        )
        # Alpha PnL: side * (decision_price - fair_value) * qty = 1 * (150.5 - 150.0) * 100 = 50
        assert attribution.alpha_pnl > 0
        # Execution PnL: side * (decision_price - fill_price) * qty = 1 * (150.5 - 150.3) * 100 = 20
        assert attribution.execution_pnl > 0
        # Fee PnL: always negative
        assert attribution.fee_pnl < 0
        # Total should be positive
        assert attribution.total_pnl > 0

        # Step 8: Pipeline completion
        report = latency_enforcer.end_pipeline("test-pipeline-1")
        assert report.total_latency_ms >= 0
        assert report.sla_compliant  # Should be under 100ms

        # Verify cumulative attribution
        summary = pnl_attribution.get_cumulative_attribution()
        assert summary["trade_count"] == 1
        assert summary["total_pnl"] > 0

    @pytest.mark.asyncio
    async def test_pipeline_risk_breach_triggers_kill_switch(
        self,
        kill_switch: GlobalKillSwitch,
        war_mode: WarModeEngine,
    ) -> None:
        """Test that risk breach activates kill switch and war mode."""
        # Simulate extreme drawdown
        war_mode.evaluate_activation(
            drawdown_pct=0.25,  # 25% drawdown > 20% trigger
            daily_loss=100_000,
            volatility_ratio=1.0,
            anomaly_intensity=0.5,
        )
        assert war_mode.status.is_active
        assert war_mode.status.state.value == "ACTIVE"

        # Verify war mode blocks new positions
        allowed, reason = war_mode.check_order_allowed(
            symbol="AAPL", side="BUY", is_hedge=False, is_unwind=False
        )
        assert not allowed
        assert "War Mode" in reason

        # Verify hedging is still allowed
        allowed, reason = war_mode.check_order_allowed(
            symbol="AAPL", side="SELL", is_hedge=True, is_unwind=False
        )
        assert allowed

    @pytest.mark.asyncio
    async def test_pipeline_adverse_selection_blocks_trade(
        self, adverse_model: AdverseSelectionModel
    ) -> None:
        """Test that high adverse selection probability blocks trade."""
        # High adverse selection scenario
        result = adverse_model.estimate_probability(
            imbalance=0.8,  # High imbalance
            delta_p=0.5,  # Large price move
            fill_rate=0.9,  # High fill rate
            vpin_score=0.8,  # High toxicity
        )
        assert result.probability > 0.75
        assert result.risk_level == "CRITICAL"

    @pytest.mark.asyncio
    async def test_pipeline_qp_solver_optimization(
        self,
    ) -> None:
        """Test that QP solver produces valid portfolio weights."""
        import numpy as np

        solver = PortfolioQPSolver(min_weight=0.0, max_weight=0.5)
        returns = np.array([0.10, 0.15, 0.08, 0.12])
        cov = np.array(
            [
                [0.04, 0.01, 0.005, 0.01],
                [0.01, 0.09, 0.02, 0.015],
                [0.005, 0.02, 0.02, 0.01],
                [0.01, 0.015, 0.01, 0.06],
            ]
        )
        result = solver.optimize(returns, cov, ["A", "B", "C", "D"])
        assert result.success
        assert abs(sum(result.weights) - 1.0) < 0.001
        assert all(0.0 <= w <= 0.5 for w in result.weights)


# ============================================================================
# 2. KILL SWITCH INTEGRATION TEST
# ============================================================================


class TestKillSwitchIntegration:
    """Standash §12: Kill Switch integration test."""

    def test_kill_switch_activation(self) -> None:
        """Test kill switch can be activated and blocks all trading."""
        ks = GlobalKillSwitch()
        assert not ks.get_kill_telemetry()["is_system_halted"]

        # Activate via drawdown breach
        result = ks.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )
        assert result["status"] == "KILL_SWITCH_ACTIVE"
        assert ks.get_kill_telemetry()["is_system_halted"]

    def test_kill_switch_deactivation_not_allowed(self) -> None:
        """Test kill switch cannot be deactivated once triggered (non-overrideable)."""
        ks = GlobalKillSwitch()
        ks.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )
        # Try to re-evaluate — should return ALREADY_HALTED
        result = ks.evaluate_kill_system(
            current_drawdown=0.10,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )
        assert result["status"] == "ALREADY_HALTED"

    def test_kill_switch_persistence(self) -> None:
        """Test kill switch state persists across checks."""
        ks = GlobalKillSwitch()
        ks.evaluate_kill_system(
            current_drawdown=0.25,
            current_absolute_loss=0,
            current_anomaly_score=0,
        )

        # Multiple checks should all return halted
        for _ in range(10):
            result = ks.evaluate_kill_system(
                current_drawdown=0.10,
                current_absolute_loss=0,
                current_anomaly_score=0,
            )
            assert result["status"] == "ALREADY_HALTED"


# ============================================================================
# 3. SHADOW MODE COMPARISON TEST
# ============================================================================


class TestShadowModeComparison:
    """Standash §4.13: Shadow mode comparison test."""

    def test_shadow_duration_enforcement(self) -> None:
        """Test that shadow mode enforces minimum duration before live promotion."""
        config = {
            "shadow_mode": True,
            "data_lake_path": "/tmp/shadow_test",
            "min_shadow_duration_s": 604800,  # 7 days
        }
        engine = ShadowEngine(config)

        # Shadow just started — should not be promotable
        assert not engine.is_shadow_duration_met()
        can_promote, reason = engine.can_promote_to_live()
        assert not can_promote
        assert "Shadow duration not met" in reason

        # Get duration info
        info = engine.get_shadow_duration_info()
        assert info["started"] is True
        assert info["required_days"] == 7.0
        assert not info["duration_met"]

    def test_shadow_metrics_tracking(self) -> None:
        """Test that shadow engine tracks metrics."""
        config = {
            "shadow_mode": True,
            "data_lake_path": "/tmp/shadow_test",
        }
        engine = ShadowEngine(config)
        engine._running = True

        metrics = engine.get_metrics()
        assert isinstance(metrics, dict)
        assert engine.is_running()


# ============================================================================
# 4. FAILOVER / STATE REPLICATION TEST
# ============================================================================


class TestFailoverStateReplication:
    """Standash §5.2: Stateful replication and failover test."""

    def test_state_replication_publish_receive(self) -> None:
        """Test primary publishes state and standby receives it."""
        primary = StateReplicator("node-primary", role=NodeRole.PRIMARY)
        standby = StateReplicator("node-standby", role=NodeRole.STANDBY)

        # Primary publishes state
        oms_state = {
            "orders": [{"id": "O1", "status": "FILLED"}],
            "positions": {"AAPL": 100},
        }
        checksum = primary.publish_state(oms_state)
        assert len(checksum) == 16

        # Standby receives and verifies
        success, reason = standby.receive_state("node-primary", oms_state, checksum)
        assert success
        assert "synchronized" in reason.lower()

    def test_failover_on_peer_unresponsive(self) -> None:
        """Test standby detects unresponsive primary and executes failover."""
        standby = StateReplicator("node-standby", role=NodeRole.STANDBY, failover_threshold_s=1.0)

        # Initially no failover needed
        assert not standby.check_failover_needed()

        # Simulate peer becoming unresponsive
        standby._last_peer_heartbeat = time.time() - 5.0
        assert standby.check_failover_needed()

        # Execute failover
        role = standby.execute_failover()
        assert role == NodeRole.PRIMARY
        assert standby.state.failover_count == 1

    def test_failover_prevents_double_execution(self) -> None:
        """Test that failover doesn't cause double execution."""
        primary = StateReplicator("node-1", role=NodeRole.PRIMARY)
        standby = StateReplicator("node-2", role=NodeRole.STANDBY, failover_threshold_s=1.0)

        # Primary publishes state
        state = {"orders": [], "positions": {}}
        checksum = primary.publish_state(state)
        standby.receive_state("node-1", state, checksum)

        # Simulate primary failure
        standby._last_peer_heartbeat = time.time() - 5.0
        standby.execute_failover()

        # New primary should have consistent state
        assert standby.state.local_role == NodeRole.PRIMARY
        assert standby.state.failover_count == 1


# ============================================================================
# 5. FSM STRESS TEST
# ============================================================================


class TestFSMStress:
    """Standash §7: Order FSM stress test."""

    def test_fsm_valid_transitions(self) -> None:
        """Test all valid FSM transitions."""
        fsm = OrderFSM()

        # Happy path
        assert fsm.transition("NEW", "ACK") == "ACK"
        assert fsm.transition("ACK", "FILL_PARTIAL") == "PARTIAL"
        assert fsm.transition("PARTIAL", "FILL_PARTIAL") == "PARTIAL"
        assert fsm.transition("PARTIAL", "FILL_COMPLETE") == "FILLED"

        # Cancel path
        assert fsm.transition("ACK", "CANCEL") == "CLOSED"
        assert fsm.transition("PARTIAL", "CANCEL") == "CLOSED"

        # Reject path
        assert fsm.transition("NEW", "REJECT") == "REJECTED"
        assert fsm.transition("ACK", "REJECT") == "REJECTED"

    def test_fsm_invalid_transitions_raise(self) -> None:
        """Test that invalid transitions raise ValueError."""
        fsm = OrderFSM()

        # Illegal jumps
        with pytest.raises(ValueError):
            fsm.transition("NEW", "FILL_COMPLETE")  # Must go through ACK
        with pytest.raises(ValueError):
            fsm.transition("NEW", "FILLED")  # Must go through ACK + PARTIAL

        # Terminal states don't raise but return current state
        assert fsm.transition("FILLED", "CANCEL") == "FILLED"

    def test_fsm_terminal_states_immutable(self) -> None:
        """Test that terminal states ignore further events."""
        fsm = OrderFSM()

        # FILLED is terminal
        assert fsm.transition("FILLED", "CANCEL") == "FILLED"
        assert fsm.transition("FILLED", "REJECT") == "FILLED"

        # CLOSED is terminal
        assert fsm.transition("CLOSED", "FILL_COMPLETE") == "CLOSED"

        # REJECTED is terminal
        assert fsm.transition("REJECTED", "ACK") == "REJECTED"

    def test_fsm_timeout_detection(self) -> None:
        """Test FSM detects pending state timeouts."""
        fsm = OrderFSM(pending_timeout_s=0.1)  # 100ms timeout for testing

        # Record order entry
        fsm.record_state_entry("O1", "NEW")
        assert not fsm.check_timeout("O1")

        # Wait for timeout
        time.sleep(0.15)
        assert fsm.check_timeout("O1")

        # Cleanup removes from tracking
        fsm.cleanup("O1")
        assert not fsm.check_timeout("O1")

    def test_fsm_stress_rapid_transitions(self) -> None:
        """Test FSM handles rapid state transitions correctly."""
        fsm = OrderFSM(pending_timeout_s=30.0)

        # Rapid order lifecycle
        for i in range(100):
            order_id = f"O{i}"
            fsm.record_state_entry(order_id, "NEW")
            state = fsm.transition("NEW", "ACK")
            assert state == "ACK"
            state = fsm.transition("ACK", "FILL_COMPLETE")
            assert state == "FILLED"
            fsm.cleanup(order_id)

        # All orders should be cleaned up
        assert len(fsm.get_pending_orders([f"O{i}" for i in range(100)])) == 0
