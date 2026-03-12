from typing import Dict, Any, List
import json
from pathlib import Path

class FeatureRegistry:
    """Registry to track factor metadata and ensure offline/online parity."""
    
    def __init__(self, registry_path: str = "qtrader/features/registry.json") -> None:
        self.path = Path(registry_path)
        self.registry: Dict[str, Any] = {}
        self.load()

    def register_feature(self, name: str, category: str, params: Dict[str, Any]) -> None:
        """Registers a feature with its metadata."""
        self.registry[name] = {
            "category": category,
            "params": params,
            "version": "1.0.0"
        }
        self.save()

    def get_features_by_category(self, category: str) -> List[str]:
        return [name for name, meta in self.registry.items() if meta["category"] == category]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(self.registry, f, indent=4)

    def load(self) -> None:
        if self.path.exists():
            with open(self.path, "r") as f:
                self.registry = json.load(f)
