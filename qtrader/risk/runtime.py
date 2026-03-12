import logging
from qtrader.core.event import RiskEvent

class RuntimeRiskEngine:
    """Real-time monitoring and safety guardrails."""
    
    def __init__(self, max_drawdown: float = 0.1, max_exposure: float = 1000000.0) -> None:
        self.max_drawdown = max_drawdown
        self.max_exposure = max_exposure
        self.current_drawdown = 0.0
        self.current_exposure = 0.0
        self.is_active = True

    def check_breach(self) -> bool:
        """Checks if any safety limits have been breached."""
        if not self.is_active:
            return False
            
        if self.current_drawdown > self.max_drawdown:
            logging.critical("CRITICAL: Max Drawdown breached. Triggering Kill Switch.")
            return True
            
        if self.current_exposure > self.max_exposure:
            logging.warning("WARNING: Max Exposure breached.")
            return True
            
        return False

    def trigger_kill_switch(self) -> RiskEvent:
        """Stops all trading activities and flattens positions."""
        self.is_active = False
        return RiskEvent(
            reason="Safety limit breached",
            action="LIQUIDATE_AND_HALT"
        )
