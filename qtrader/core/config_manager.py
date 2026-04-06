from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from qtrader.core.events import ConfigChangeEvent, ConfigChangePayload

if TYPE_CHECKING:
    from qtrader.core.event_store import BaseEventStore

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Versioned Dynamic Configuration Manager.
    
    Allows runtime control of system behavior without redeployment, ensuring safety 
    through linear versioning and bit-perfect rollbacks.
    
    Architecture:
    - Immutable Snapshots: Every change results in a new versioned snapshot of the whole config.
    - Authoritative History: All changes are recorded in the EventStore for audit and recovery.
    """

    def __init__(
        self, 
        initial_config: dict[str, Any] | None = None, 
        event_store: BaseEventStore | None = None
    ) -> None:
        """
        Initialize the ConfigManager.
        
        Args:
            initial_config: The seed configuration for version 1.
            event_store: Authoritative source for change logs and persistence.
        """
        self._current_version = 1
        # Mapping of Version -> Full Config Snapshot
        self._history: dict[int, dict[str, Any]] = {
            1: initial_config or {}
        }
        self._event_store = event_store

    def get_current_version(self) -> int:
        """Return the current system configuration version."""
        return self._current_version

    def is_loaded(self) -> bool:
        """
        Check if the configuration has been loaded into memory.
        Returns True if at least one version snapshot exists.
        """
        return self._current_version >= 1 and len(self._history) > 0

    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve the current configuration value for a specific key.
        
        Args:
            key: The configuration parameter name.
            default: Fallback value if key is not found.
        """
        return self._history[self._current_version].get(key, default)

    async def update(self, key: str, value: Any, trace_id: UUID | None = None) -> ConfigChangeEvent:
        """
        Update a configuration parameter and increment the system-wide version.
        
        This method captures a full immutable snapshot of the configuration after 
        the change, ensuring perfect traceability.
        
        Args:
            key: The parameter to modify.
            value: The new validated value.
            trace_id: Correlation ID for the audit trail.
            
        Returns:
            ConfigChangeEvent: The event representing the version increment.
        """
        old_config = self._history[self._current_version]
        old_value = old_config.get(key)
        
        # 1. Linear Version Increment
        new_version = self._current_version + 1
        
        # 2. Create and Store New Snapshot
        new_config = old_config.copy()
        new_config[key] = value
        
        self._history[new_version] = new_config
        self._current_version = new_version
        
        # 3. Create Audit Event
        event = ConfigChangeEvent(
            trace_id=trace_id or uuid4(),
            source="ConfigManager",
            payload=ConfigChangePayload(
                config_key=key,
                old_value=old_value,
                new_value=value,
                version=new_version
            )
        )
        
        # 4. Authoritative Persistence
        if self._event_store:
            await self._event_store.append(event)
            
        logger.info(f"CONFIG_UPDATED | Version: {new_version} | Key: {key} -> {value}")
        return event

    async def rollback(self, version: int, trace_id: UUID | None = None) -> ConfigChangeEvent:
        """
        Revert the entire system configuration to a previous version snapshot.
        
        This generates a *new* version that is a clone of the target historical version, 
        maintaining a forward-only append-only history.
        
        Args:
            version: The historical version number to restore.
            trace_id: Correlation ID for the rollback event.
            
        Returns:
            ConfigChangeEvent: The event representing the system rollback.
        """
        if version not in self._history:
            logger.error(f"CONFIG_ROLLBACK_FAILED | Target Version {version} not found in memory.")
            raise ValueError(f"Config version {version} does not exist in history.")

        old_v = self._current_version
        target_state = self._history[version]
        
        # Create a NEW version inheriting the old state
        new_v = self._current_version + 1
        self._history[new_v] = target_state.copy()
        self._current_version = new_v
        
        event = ConfigChangeEvent(
            trace_id=trace_id or uuid4(),
            source="ConfigManager",
            payload=ConfigChangePayload(
                config_key="SYSTEM_FORCE_ROLLBACK",
                old_value=f"V{old_v}",
                new_value=f"V{version}",
                version=new_v
            )
        )
        
        if self._event_store:
            await self._event_store.append(event)
            
        logger.warning(f"CONFIG_ROLLBACK | Reverted to Snapshot V{version} | New Version: V{new_v}")
        return event
