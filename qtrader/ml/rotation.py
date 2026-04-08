import logging


class ModelRotator:
    """
    Automatically selects and activates the best model for a given market regime.
    """

    def __init__(self) -> None:
        # Map regime_id -> model_id (from Registry)
        self.regime_map: dict[int, str] = {}
        self.current_regime: int | None = None
        self.current_model_id: str | None = None

    def update_map(self, mapping: dict[int, str]) -> None:
        """Updates the regime-to-model mapping."""
        self.regime_map = mapping

    def on_regime_change(self, new_regime: int) -> str | None:
        """Triggers model rotation if the market regime has shifted."""
        if new_regime == self.current_regime:
            return self.current_model_id

        logging.info(
            "AUTONOMOUS | Market regime shift detected: %s -> %s",
            self.current_regime,
            new_regime,
        )
        self.current_regime = new_regime

        target_model = self.regime_map.get(new_regime)
        if target_model and target_model != self.current_model_id:
            logging.info(f"AUTONOMOUS | Rotating model to: {target_model}")
            self.current_model_id = target_model
            return target_model

        return self.current_model_id
