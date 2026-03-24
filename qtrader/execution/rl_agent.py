"""
Reinforcement Learning based Execution Agent.
Optimized for ultra-fast inference (<1ms) using pure Numpy.
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np

from qtrader.core.logger import logger
from qtrader.core.types import OrderEvent


class NumpyPolicyNetwork:
    """Ultra-lightweight Numpy implementation of an MLP policy."""
    def __init__(self, input_dim: int, output_dim: int):
        self.input_dim = input_dim
        self.output_dim = output_dim
        
        # Initialize small random weights for the placeholder
        # Hidden layer 1: 32 nodes, Hidden layer 2: 16 nodes
        self.w1 = np.random.randn(input_dim, 32) * 0.1
        self.b1 = np.zeros(32)
        self.w2 = np.random.randn(32, 16) * 0.1
        self.b2 = np.zeros(16)
        self.w3 = np.random.randn(16, output_dim) * 0.1
        self.b3 = np.zeros(output_dim)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass with ReLU and Softmax."""
        # Layer 1
        z1 = np.dot(x, self.w1) + self.b1
        a1 = np.maximum(0, z1)  # ReLU
        
        # Layer 2
        z2 = np.dot(a1, self.w2) + self.b2
        a2 = np.maximum(0, z2)  # ReLU
        
        # Layer 3 (Output)
        logits = np.dot(a2, self.w3) + self.b3
        
        # Softmax
        exp_logits = np.exp(logits - np.max(logits))  # Numerical stability
        result: np.ndarray = exp_logits / np.sum(exp_logits)
        return result

    def load_weights(self, weights: dict[str, np.ndarray]) -> None:
        """Load weights from a dictionary."""
        self.w1 = weights['w1']
        self.b1 = weights['b1']
        self.w2 = weights['w2']
        self.b2 = weights['b2']
        self.w3 = weights['w3']
        self.b3 = weights['b3']

class ExecutionRLAgent:
    """
    RL Agent for optimized order execution using pure Numpy.
    
    State: [Imbalance, Spread, Position Left %, Time Left %, Volatility]
    Actions: 
        Order Type: [LIMIT_BID, LIMIT_MID, LIMIT_ASK, MARKET]
        Order Size: [0%, 10%, 25%, 50%, 100%] of remaining
    """

    LATENCY_THRESHOLD_MS = 5.0

    def __init__(self, weights_path: str | None = None):
        self.input_dim = 5
        self.num_types = 4
        self.num_sizes = 5
        self.output_dim = self.num_types * self.num_sizes
        
        self.model = NumpyPolicyNetwork(self.input_dim, self.output_dim)
        
        if weights_path:
            try:
                weights = np.load(weights_path, allow_pickle=True).item()
                self.model.load_weights(weights)
                logger.info(f"Loaded RL weights from {weights_path}")
            except Exception as e:
                logger.warning(f"Failed to load RL weights: {e}. Using random weights.")

    def get_action(
        self,
        orderbook: dict[str, Any],
        remaining_qty: Decimal,
        total_qty: Decimal,
        time_left_pct: float,
        volatility: float,
    ) -> tuple[str, float]:
        """
        Get optimized execution action.
        
        Returns:
            Tuple of (order_type, quantity_ratio)
        """
        start_time = time.perf_counter()
        
        try:
            if not orderbook.get('bids') or not orderbook.get('asks'):
                raise ValueError("Empty or invalid orderbook")

            state = self._prepare_state(
                orderbook, remaining_qty, total_qty, time_left_pct, volatility
            )
            
            probs = self.model.forward(state)
            action_idx = int(np.argmax(probs))
            
            # Decompose action
            type_idx = action_idx // self.num_sizes
            size_idx = action_idx % self.num_sizes
            
            order_type = ["LIMIT_BID", "LIMIT_MID", "LIMIT_ASK", "MARKET"][type_idx]
            size_ratio = [0.0, 0.1, 0.25, 0.5, 1.0][size_idx]
            
            inference_time_ms = (time.perf_counter() - start_time) * 1000
            if inference_time_ms > self.LATENCY_THRESHOLD_MS:
                logger.warning(f"RL Inference latency: {inference_time_ms:.2f}ms")
                
            return order_type, size_ratio
            
        except Exception as e:
            logger.error(f"RL Agent failure: {e}. Falling back to default execution.")
            return "MARKET", 1.0  # Safe fallback

    def _prepare_state(
        self,
        orderbook: dict[str, Any],
        remaining_qty: Decimal,
        total_qty: Decimal,
        time_left_pct: float,
        volatility: float,
    ) -> np.ndarray:
        """Prepare normalized state vector."""
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return np.zeros(self.input_dim)
            
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        bid_vol = float(bids[0][1])
        ask_vol = float(asks[0][1])
        mid = (best_bid + best_ask) / 2
        
        # 1. Imbalance
        imbalance = (bid_vol - ask_vol) / (bid_vol + ask_vol + 1e-8)
        # 2. Spread
        spread = (best_ask - best_bid) / mid
        # 3. Position Left %
        pos_left = float(remaining_qty / total_qty) if total_qty > 0 else 0.0
        # 4. Time Left % (0.0 to 1.0)
        # 5. Volatility (normalized)
        
        state_vec = [imbalance, spread, pos_left, time_left_pct, volatility]
        return np.array(state_vec, dtype=np.float32)

    def create_order(
        self, 
        symbol: str, 
        side: str, 
        price: Decimal, 
        quantity: Decimal, 
        order_type: str
    ) -> OrderEvent:
        """Create OrderEvent based on agent decision."""
        # Convert internal agent types to core OrderEvent types
        core_type = "MARKET" if order_type == "MARKET" else "LIMIT"
        
        return OrderEvent(
            symbol=symbol,
            order_type=core_type,
            quantity=quantity,
            side=side,
            price=price,
            order_id=f"RL_{int(time.time() * 1000)}",
            timestamp=datetime.now()
        )
