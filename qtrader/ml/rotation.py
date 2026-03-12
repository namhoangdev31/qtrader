from typing import Dict, Any, Optional
import logging

class ModelRotator:
    """
    Automatically selects and activates the best model for a given market regime.
    """
    
    def __init__(self) -> None:
        # Map regime_id -> model_id (from Registry)
        self.regime_map: Dict[int, str] = {}
        self.current_regime: Optional[int] = None
        self.current_model_id: Optional[str] = None

    def update_map(self, mapping: Dict[int, str]) -> None:
        """Updates the regime-to-model mapping."""
        self.regime_map = mapping

    def on_regime_change(self, new_regime: int) -> Optional[str]:
        """Triggers model rotation if the market regime has shifted."""
        if new_regime == self.current_regime:
            return self.current_model_id
            
        logging.info(f"AUTONOMOUS | Market regime shift detected: {self.current_regime} -> {new_regime}")
        self.current_regime = new_regime
        
        target_model = self.regime_map.get(new_regime)
        if target_model and target_model != self.current_model_id:
            logging.info(f"AUTONOMOUS | Rotating model to: {target_model}")
            self.current_model_id = target_model
            return target_model
            
        return self.current_model_id
