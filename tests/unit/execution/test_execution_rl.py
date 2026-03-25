import pytest
import time
from decimal import Decimal
import numpy as np
from qtrader.execution.rl_agent import ExecutionRLAgent

@pytest.fixture
def agent() -> ExecutionRLAgent:
    return ExecutionRLAgent()

@pytest.fixture
def mock_orderbook() -> dict:
    return {
        'bids': [(Decimal('100.0'), Decimal('1000.0')), (Decimal('99.9'), Decimal('500.0'))],
        'asks': [(Decimal('101.0'), Decimal('1000.0')), (Decimal('101.1'), Decimal('500.0'))],
        'timestamp': time.time()
    }

def test_rl_agent_inference_latency(agent, mock_orderbook):
    """Test that RL inference is extremely fast (<1ms)."""
    # Warm up
    agent.get_action(mock_orderbook, Decimal('10.0'), Decimal('100.0'), 0.5, 0.01)
    
    times = []
    for _ in range(100):
        start = time.perf_counter()
        agent.get_action(mock_orderbook, Decimal('10.0'), Decimal('100.0'), 0.5, 0.01)
        times.append((time.perf_counter() - start) * 1000)
    
    avg_latency = sum(times) / len(times)
    # Numpy should be <1ms on modern CPUs
    assert avg_latency < 1.0, f"Average latency {avg_latency:.4f}ms exceeds 1ms"

def test_rl_agent_state_prep(agent, mock_orderbook):
    """Test that state vector is correctly formed and normalized."""
    state = agent._prepare_state(
        mock_orderbook, 
        remaining_qty=Decimal('50.0'), 
        total_qty=Decimal('100.0'), 
        time_left_pct=0.5, 
        volatility=0.01
    )
    
    assert isinstance(state, np.ndarray)
    assert state.shape == (5,)
    # pos_left should be 0.5
    assert abs(state[2] - 0.5) < 1e-6
    # time_left should be 0.5
    assert abs(state[3] - 0.5) < 1e-6

def test_rl_agent_action_decomposition(agent, mock_orderbook):
    """Test that get_action returns valid actions even with random weights."""
    order_type, size_ratio = agent.get_action(
        mock_orderbook, Decimal('10.0'), Decimal('100.0'), 0.5, 0.01
    )
    
    assert order_type in ["LIMIT_BID", "LIMIT_MID", "LIMIT_ASK", "MARKET"]
    assert size_ratio in [0.0, 0.1, 0.25, 0.5, 1.0]

def test_rl_agent_fallback_on_error(agent):
    """Test that agent falls back to MARKET/1.0 on errors."""
    # Pass invalid orderbook to trigger error
    order_type, size_ratio = agent.get_action(
        {}, Decimal('10.0'), Decimal('100.0'), 0.5, 0.01
    )
    assert order_type == "MARKET"
    assert size_ratio == 1.0
