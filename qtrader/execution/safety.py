import logging
import time
from typing import Any

from qtrader.core.event import OrderEvent


class SafetyLayer:
    """
    Final guardrail between Risk management and Execution.
    Detects market anomalies and halts autonomous flows.
    """
    
    def __init__(self) -> None:
        self.last_order_time = 0.0
        self.order_count_window = []
        self.max_orders_per_sec = 10
        self.is_halted = False
        
        # Thresholds for Flash Crash detection
        self.max_spread_pct = 0.05 # 5% spread explosion
        self.min_liquidity_depth = 1000.0 # Min depth required to trade

    def check_order(self, order: OrderEvent, market_state: dict[str, Any]) -> bool:
        """Runs safety checks before allowing an order to hit the exchange."""
        if self.is_halted:
            logging.error("SAFETY | Order REJECTED: System is HALTED")
            return False

        # 1. Rate Limiting Check
        now = time.time()
        self.order_count_window = [t for t in self.order_count_window if now - t < 1.0]
        if len(self.order_count_window) >= self.max_orders_per_sec:
            logging.error("SAFETY | Rate Limit Exceeded: Throttling orders")
            return False
            
        # 2. Flash Crash / Spread Detection
        spread = market_state.get("spread_pct", 0.0)
        if spread > self.max_spread_pct:
            self.halt_system("Spread Explosion Detected")
            return False
            
        # 3. Liquidity Guard
        depth = market_state.get("top_depth", 0.0)
        if depth < self.min_liquidity_depth:
            self.halt_system("Liquidity Vacuum Detected")
            return False

        self.order_count_window.append(now)
        return True

    def halt_system(self, reason: str) -> None:
        """Triggers a global emergency halt."""
        logging.critical(f"SAFETY | EMERGENCY HALT TRIGGERED: {reason}")
        self.is_halted = True
        # Future: Trigger 'Flatten All' command to OMS
