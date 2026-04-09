from __future__ import annotations

import logging
from enum import IntEnum

from qtrader.core.events import EventType

logger = logging.getLogger(__name__)


class EventPriority(IntEnum):
    LOW = 0
    NORMAL = 1
    CRITICAL = 2


class BackpressureController:
    def __init__(
        self,
        warning_threshold: int = 2000,
        throttle_threshold: int = 5000,
        reject_threshold: int = 10000,
    ) -> None:
        self.warning_threshold = warning_threshold
        self.throttle_threshold = throttle_threshold
        self.reject_threshold = reject_threshold

    def get_priority(self, event_type: EventType) -> EventPriority:
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
        priority = self.get_priority(event_type)
        if priority == EventPriority.CRITICAL:
            return False
        if queue_size > self.warning_threshold and priority == EventPriority.LOW:
            return True
        if queue_size > self.throttle_threshold and priority == EventPriority.NORMAL:
            return True
        return False

    def should_throttle(self, queue_size: int) -> bool:
        return queue_size > self.throttle_threshold
