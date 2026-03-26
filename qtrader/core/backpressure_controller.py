from __future__ import annotations

import logging
from enum import IntEnum, auto

from qtrader.core.events import EventType

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class BackpressureController:
    """
    Monitor and control event flow to prevent system exhaustion.
    Provides thresholds for warning, throttling, and rejection.
    """

    def __init__(
        self,
        warning_threshold: int = 2000,
        throttle_threshold: int = 5000,
        reject_threshold: int = 10000
    ):
        """
        Initialize thresholds for backpressure.
        
        Args:
            warning_threshold: Log warnings above this depth.
            throttle_threshold: Slow down producers above this depth.
            reject_threshold: Drop or error above this depth.
        """
        self.warning_threshold = warning_threshold
        self.throttle_threshold = throttle_threshold
        self.reject_threshold = reject_threshold

    def get_priority(self, event_type: EventType) -> EventPriority:
        """
        Determine the importance of an event type.
        """
        critical_types = {
            EventType.ORDER,
            EventType.FILL,
            EventType.RISK,
            EventType.SIGNAL,
            EventType.GAP_DETECTED,
            EventType.SYSTEM,
            EventType.ERROR,
        }
        low_priority_types = {
            EventType.HEARTBEAT,
            EventType.CLOCK_SYNC,
            EventType.FEEDBACK_UPDATE,
            EventType.DRIFT,
        }
        
        if event_type in critical_types:
            return EventPriority.CRITICAL
        if event_type in low_priority_types:
            return EventPriority.LOW
        return EventPriority.NORMAL

    def should_drop(self, queue_size: int, event_type: EventType) -> bool:
        """
        Decide whether to drop an incoming event based on current load and priority.
        """
        priority = self.get_priority(event_type)
        
        # Never drop CRITICAL events
        if priority == EventPriority.CRITICAL:
            return False
            
        # Drop LOW priority events early if under pressure
        if queue_size > self.warning_threshold and priority == EventPriority.LOW:
            return True
            
        # Drop NORMAL priority if approaching peak capacity
        if queue_size > self.throttle_threshold and priority == EventPriority.NORMAL:
            return True
            
        return False

    def should_throttle(self, queue_size: int) -> bool:
        """
        Indicate whether producers should be throttled.
        """
        return queue_size > self.throttle_threshold
