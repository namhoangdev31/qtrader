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

    async def halt_system(self, reason: str, oms: Any | None = None) -> None:
        """Triggers a global emergency halt."""
        logging.critical(f"SAFETY | EMERGENCY HALT TRIGGERED: {reason}")
        self.is_halted = True
        if oms:
            await oms.cancel_all_orders()


class ShadowEnforcer:
    """[SHADOW_ENFORCEMENT] Safety gate that requires 7 days of verified shadow performance."""

    def __init__(self, shadow_data_path: str = "data_lake/shadow") -> None:
        self.shadow_data_path = shadow_data_path
        self.required_shadow_days = 7

    def verify_history(self) -> bool:
        """Validate if the current strategy has at least 7 days of shadow history."""
        import os
        from glob import glob
        
        if not os.path.exists(self.shadow_data_path):
            return False
            
        # Count unique dates from shadow_fills_YYYYMMDD.jsonl
        pattern = os.path.join(self.shadow_data_path, "shadow_fills_*.jsonl")
        fill_files = glob(pattern)
        
        # Extract unique dates from filenames
        unique_days = set()
        for f in fill_files:
            # name = "shadow_fills_20240101.jsonl"
            basename = os.path.basename(f)
            parts = basename.replace(".jsonl", "").split("_")
            if len(parts) >= 3:
                unique_days.add(parts[2])
                
        count = len(unique_days)
        if count < self.required_shadow_days:
            logging.error(f"SHADOW_ENFORCEMENT | Strategy REJECTED: Only {count}/{self.required_shadow_days} shadow days found.")
            return False
            
        logging.info(f"SHADOW_ENFORCEMENT | Verified strategy for live trading ({count} shadow days).")
        return True
