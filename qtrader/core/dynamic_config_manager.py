from __future__ import annotations

import time
from typing import Any

from loguru import logger

from qtrader.core.config_loader import ConfigLoader, QTraderConfig
from qtrader.core.events import ConfigChangeEvent, ConfigChangePayload


class DynamicConfigManager:
    """
    Manages runtime configuration updates with safety enforcement.
    Ensures that updates are atomic, validated, and within safety bounds.
    """

    def __init__(
        self, 
        config_event_bus: Any | None = None,
        max_history: int = 10,
        leverage_delta_limit: float = 0.5  # Max 50% change in leverage per update
    ) -> None:
        self._event_bus = config_event_bus
        self._max_history = max_history
        self._leverage_delta_limit = leverage_delta_limit
        self._history: list[QTraderConfig] = []
        
        # Metrics
        self.update_count: int = 0
        self.failure_count: int = 0
        self.rollback_count: int = 0

    async def update_config(self, delta: dict[str, Any]) -> bool:
        """
        Apply a delta to the current configuration.
        
        Args:
            delta: Nested dictionary representing the changes to apply.
        
        Returns:
            bool: True if the update was successful, False otherwise.
        """
        current_config = ConfigLoader.load()
        self._history.append(current_config)
        
        # Keep history within limits
        if len(self._history) > self._max_history:
            self._history.pop(0)

        try:
            # 1. Deep copy and apply delta manually
            new_data = current_config.model_dump()
            self._apply_delta(new_data, delta)
            
            # 2. Re-validate via Pydantic
            new_config = QTraderConfig.model_validate(new_data)
            
            # 3. Enforce Safety Bounds (e.g. Max Delta)
            self._enforce_safety_bounds(current_config, new_config)
            
            # 4. Atomic Swap in loader
            ConfigLoader.update_instance(new_config)
            
            # 5. Broadcast changes
            if self._event_bus:
                for section, values in delta.items():
                    if isinstance(values, dict):
                        for key, val in values.items():
                            event = self._create_change_event(
                                key=f"{section}.{key}",
                                old_val=getattr(getattr(current_config, section), key),
                                new_val=val,
                                version=int(time.time())
                            )
                            await self._event_bus.publish_change(event)
            
            self.update_count += 1
            logger.success(f"[DYNAMIC-CONFIG] Successfully updated {len(delta)} sections")
            return True

        except Exception as e:
            self.failure_count += 1
            logger.error(f"[DYNAMIC-CONFIG] Update rejected: {e}")
            # Rollback to the previous state just in case
            if self._history:
                ConfigLoader.update_instance(self._history.pop())
            return False

    async def rollback(self) -> bool:
        """Revert to the last known valid configuration."""
        if not self._history:
            logger.warning("[DYNAMIC-CONFIG] No history available for rollback")
            return False
            
        previous_config = self._history.pop()
        ConfigLoader.update_instance(previous_config)
        self.rollback_count += 1
        logger.warning(f"[DYNAMIC-CONFIG] Rollback complete. Restored version: {previous_config.version}")
        
        # Broadcast rollback as a generic config change
        if self._event_bus:
            # Broadcast as a catch-all update
            pass 
            
        return True

    def _apply_delta(self, target: dict, delta: dict) -> None:
        """Recursively apply delta to target dictionary."""
        for k, v in delta.items():
            if isinstance(v, dict) and k in target and isinstance(target[k], dict):
                self._apply_delta(target[k], v)
            else:
                target[k] = v

    def _enforce_safety_bounds(self, old: QTraderConfig, new: QTraderConfig) -> None:
        """Mathematical safety constraints on parameter drift."""
        
        # Leverage Delta Limit: ||C_new - C_old|| ≤ ε_safe
        old_lev = old.risk.max_leverage
        new_lev = new.risk.max_leverage
        
        if abs(new_lev - old_lev) / old_lev > self._leverage_delta_limit:
            raise ValueError(
                f"Leverage drift {new_lev - old_lev:.2f} exceeds safety limit "
                f"of {self._leverage_delta_limit * 100}%"
            )

    def _create_change_event(self, key: str, old_val: Any, new_val: Any, version: int) -> ConfigChangeEvent:
        """Helper to create a ConfigChangeEvent."""
        payload = ConfigChangePayload(
            config_key=key,
            old_value=old_val,
            new_value=new_val,
            version=version
        )
        return ConfigChangeEvent(source="DynamicConfigManager", payload=payload)

    def get_status(self) -> dict[str, Any]:
        """Return enforcement status for observability."""
        return {
            "status": "DYNAMIC_ENABLED",
            "updates": self.update_count,
            "failures": self.failure_count,
            "rollbacks": self.rollback_count
        }
