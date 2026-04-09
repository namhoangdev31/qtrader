import logging


class ModelRotator:
    def __init__(self) -> None:
        self.regime_map: dict[int, str] = {}
        self.current_regime: int | None = None
        self.current_model_id: str | None = None

    def update_map(self, mapping: dict[int, str]) -> None:
        self.regime_map = mapping

    def on_regime_change(self, new_regime: int) -> str | None:
        if new_regime == self.current_regime:
            return self.current_model_id
        logging.info(
            "AUTONOMOUS | Market regime shift detected: %s -> %s", self.current_regime, new_regime
        )
        self.current_regime = new_regime
        target_model = self.regime_map.get(new_regime)
        if target_model and target_model != self.current_model_id:
            logging.info(f"AUTONOMOUS | Rotating model to: {target_model}")
            self.current_model_id = target_model
            return target_model
        return self.current_model_id
