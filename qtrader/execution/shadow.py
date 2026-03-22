import logging
from typing import Any

from qtrader.core.event import OrderEvent, SignalEvent


class ShadowTrader:
    """
    Runs a model in 'Shadow Mode'.
    Logs signals and orders but skips actual execution.
    Compares shadow PnL with predicted PnL.
    """
    
    def __init__(self, strategy_id: str) -> None:
        self.strategy_id = strategy_id
        self.shadow_orders: list[OrderEvent] = []
        self.is_active = True

    def process_signal(self, signal: SignalEvent) -> None:
        """Logs and processes a shadow signal."""
        if not self.is_active:
            return
            
        logging.info(f"SHADOW | Strategy {self.strategy_id} generated signal: {signal.value}")
        # Logic to calculate shadow fills and pnl...
        
    def log_shadow_fill(self, fill: dict[str, Any]) -> None:
        """Records a simulated fill for tracking PnL."""
        logging.info(f"SHADOW | Recorded fill for {self.strategy_id}: {fill}")
