import numpy as np
import time
import logging
from typing import Optional

class RotationHysteresis:
    """
    Prevents regime oscillation by enforcing persistence and cooldowns.
    """
    
    def __init__(self, persistence_bars: int = 5, cooldown_sec: int = 1800) -> None:
        self.persistence_bars = persistence_bars
        self.cooldown_sec = cooldown_sec
        
        self.pending_regime: Optional[int] = None
        self.pending_count = 0
        self.last_rotation_time = 0.0
        self.current_regime: Optional[int] = None

    def validate_shift(self, new_regime: int) -> bool:
        """Returns True if the regime shift meets stability criteria."""
        now = time.time()
        
        # 1. Cooldown check
        if now - self.last_rotation_time < self.cooldown_sec:
            return False
            
        # 2. Persistence check (Inertia)
        if new_regime == self.current_regime:
            self.pending_regime = None
            self.pending_count = 0
            return False
            
        if new_regime == self.pending_regime:
            self.pending_count += 1
        else:
            self.pending_regime = new_regime
            self.pending_count = 1
            
        if self.pending_count >= self.persistence_bars:
            logging.info(f"STABILITY | Regime shift confirmed after {self.pending_count} bars.")
            self.current_regime = new_regime
            self.last_rotation_time = now
            return True
            
        return False
