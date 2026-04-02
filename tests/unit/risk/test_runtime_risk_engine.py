import uuid
from decimal import Decimal

import pytest

from qtrader.core.events import OrderEvent, OrderPayload, RiskApprovedEvent, RiskRejectedEvent
from qtrader.core.state_store import Position, RiskState, SystemState
from qtrader.risk.constraints import (
    MaxExposureConstraint,
    MaxLeverageConstraint,
    VaRLimitConstraint,
)
from qtrader.risk.runtime_risk_engine import RuntimeRiskEngine


def test_risk_gate_exposure_violation():
    """Verify that orders pusing gross exposure over the hard limit are rejected."""
    # 1. Current State: 20 BTC @ 50,000 = $1,000,000 Gross Exposure
    state = SystemState(
        portfolio_value=Decimal('5000000'), # $5M NAV
        positions={
            "BTC/USD": Position(
                symbol="BTC/USD", 
                quantity=Decimal('20'), 
                market_value=Decimal('1000000'), 
                average_price=Decimal('50000')
            )
        }
    )
    
    # 2. Hard Stake: $1.5M Max Gross
    engine = RuntimeRiskEngine()
    engine.register_rule(MaxExposureConstraint(max_exposure=Decimal('1500000')))
    
    # 3. Aggressive Order: Buy 15 more BTC @ 50,000 = +$750,000 Exposure
    # Total Pro-Forma = 1,000,000 + 750,000 = 1,750,000 (VIOLATION)
    order = OrderEvent(
        trace_id=uuid.uuid4(),
        source="StrategyNode_A",
        payload=OrderPayload(
            order_id="ORD_EXP_01",
            symbol="BTC/USD",
            action="BUY",
            quantity=15.0,
            price=50000.0
        )
    )
    
    decision = engine.evaluate(order, state)
    
    assert isinstance(decision, RiskRejectedEvent)
    assert decision.payload.reason == "MAX_EXPOSURE_VIOLATION"
    assert decision.payload.metric_value == 1750000.0
    assert decision.payload.threshold == 1500000.0


def test_risk_gate_leverage_violation():
    """Verify that orders pushing total leverage over the hard limit are rejected."""
    # 1. Current State: $1M NAV, $1.8M Gross Exposure (Leverage = 1.8x)
    state = SystemState(
        portfolio_value=Decimal('1000000'),
        positions={
            "ETH/USD": Position(
                symbol="ETH/USD", 
                quantity=Decimal('600'), 
                market_value=Decimal('1800000'), 
                average_price=Decimal('3000')
            )
        }
    )
    
    # 2. Hard Gate: 2.0x Max Leverage
    engine = RuntimeRiskEngine()
    engine.register_rule(MaxLeverageConstraint(max_leverage=Decimal('2.0')))
    
    # 3. Order: Buy 100 ETH @ 3000 = +$300,000 Gross
    # Total Pro-Forma Gross = 1,800,000 + 300,000 = 2,100,000
    # Leverage = 2.1M / 1M = 2.1x (VIOLATION)
    order = OrderEvent(
        trace_id=uuid.uuid4(),
        source="StrategyNode_B",
        payload=OrderPayload(
            order_id="ORD_LEV_01",
            symbol="ETH/USD",
            action="BUY",
            quantity=100.0,
            price=3000.0
        )
    )
    
    decision = engine.evaluate(order, state)
    
    assert isinstance(decision, RiskRejectedEvent)
    assert decision.payload.reason == "MAX_LEVERAGE_VIOLATION"
    assert decision.payload.metric_value == 2.1


def test_risk_gate_var_violation():
    """Verify that portfolio VaR violations cause hard rejections."""
    # 1. Current State: VaR = 0.04
    state = SystemState(
        portfolio_value=Decimal('1000000'),
        risk_state=RiskState(portfolio_var=Decimal('0.04'))
    )
    
    # 2. Hard Gate: VaR Limit 0.05
    engine = RuntimeRiskEngine()
    engine.register_rule(VaRLimitConstraint(var_limit=Decimal('0.05')))
    
    # 3. Simulate high-VaR state update
    state.risk_state.portfolio_var = Decimal('0.06')
    
    order = OrderEvent(
        trace_id=uuid.uuid4(),
        source="StrategyNode_C",
        payload=OrderPayload(order_id="ORD_VAR_01", symbol="BTC/USD", action="BUY", quantity=1.0)
    )
    
    decision = engine.evaluate(order, state)
    assert isinstance(decision, RiskRejectedEvent)
    assert decision.payload.reason == "VAR_LIMIT_VIOLATION"


def test_benchmarking_risk_latency():
    """Benchmark risk decision latency to ensure sub-millisecond performance."""
    import time
    state = SystemState(portfolio_value=Decimal('1000000'))
    engine = RuntimeRiskEngine()
    engine.register_rule(MaxExposureConstraint(max_exposure=Decimal('5000000')))
    engine.register_rule(MaxLeverageConstraint(max_leverage=Decimal('5.0')))
    
    order = OrderEvent(
        trace_id=uuid.uuid4(),
        source="BENCHMARK",
        payload=OrderPayload(order_id="BENCH_01", symbol="BTC/USD", action="BUY", quantity=1.0, price=50000.0)
    )
    
    t0 = time.perf_counter()
    num_runs = 100
    for _ in range(num_runs):
        engine.evaluate(order, state)
    
    avg_latency_ms = ((time.perf_counter() - t0) / num_runs) * 1000
    print(f"\nAverage Risk Evaluation Latency: {avg_latency_ms:.4f}ms")
    
    assert avg_latency_ms < 1.0 # Strict target
