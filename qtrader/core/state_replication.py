from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.replication")


class NodeRole(str, Enum):
    PRIMARY = "PRIMARY"
    STANDBY = "STANDBY"
    FAILOVER = "FAILOVER"


@dataclass(slots=True)
class ReplicationState:
    local_role: NodeRole = NodeRole.STANDBY
    peer_node_id: str = ""
    last_sync_time: float = 0.0
    last_sync_checksum: str = ""
    pending_syncs: int = 0
    failed_syncs: int = 0
    total_syncs: int = 0
    failover_count: int = 0


class StateReplicator:
    def __init__(
        self,
        node_id: str,
        role: NodeRole = NodeRole.STANDBY,
        heartbeat_interval_s: float = 1.0,
        failover_threshold_s: float = 5.0,
    ) -> None:
        self.node_id = node_id
        self.state = ReplicationState(local_role=role)
        self.heartbeat_interval_s = heartbeat_interval_s
        self.failover_threshold_s = failover_threshold_s
        self._last_peer_heartbeat: float = 0.0
        self._local_state_checksum: str = ""
        self._replication_log: list[dict[str, Any]] = []
        self._log = logging.getLogger(f"qtrader.replication.{node_id}")

    def publish_state(self, oms_state: dict[str, Any]) -> str:
        if self.state.local_role != NodeRole.PRIMARY:
            raise RuntimeError("Only PRIMARY node can publish state")
        state_json = json.dumps(oms_state, sort_keys=True, default=str)
        checksum = hashlib.sha256(state_json.encode()).hexdigest()[:16]
        self._local_state_checksum = checksum
        self.state.last_sync_time = time.time()
        self.state.total_syncs += 1
        self._replication_log.append(
            {
                "action": "PUBLISH",
                "node_id": self.node_id,
                "checksum": checksum,
                "state_keys": list(oms_state.keys()),
                "timestamp": time.time(),
            }
        )
        self._log.debug(
            f"[REPLICATION] Published | Node: {self.node_id} | Checksum: {checksum} | Keys: {list(oms_state.keys())}"
        )
        return checksum

    def receive_state(
        self, peer_node_id: str, oms_state: dict[str, Any], checksum: str
    ) -> tuple[bool, str]:
        state_json = json.dumps(oms_state, sort_keys=True, default=str)
        computed_checksum = hashlib.sha256(state_json.encode()).hexdigest()[:16]
        if computed_checksum != checksum:
            self.state.failed_syncs += 1
            self._log.error(
                f"[REPLICATION] Checksum mismatch | Expected: {checksum} | Got: {computed_checksum}"
            )
            return (False, f"Checksum mismatch: expected {checksum}, got {computed_checksum}")
        self.state.peer_node_id = peer_node_id
        self.state.last_sync_time = time.time()
        self.state.last_sync_checksum = checksum
        self.state.total_syncs += 1
        self._last_peer_heartbeat = time.time()
        self._replication_log.append(
            {
                "action": "RECEIVE",
                "peer_node_id": peer_node_id,
                "checksum": checksum,
                "timestamp": time.time(),
            }
        )
        self._log.debug(
            f"[REPLICATION] Received | From: {peer_node_id} | Checksum: {checksum} | Verified OK"
        )
        return (True, "State synchronized successfully")

    def send_heartbeat(self) -> None:
        self._log.debug(f"[REPLICATION] Heartbeat | Node: {self.node_id}")

    def receive_heartbeat(self, peer_node_id: str) -> None:
        self._last_peer_heartbeat = time.time()
        self.state.peer_node_id = peer_node_id

    def check_failover_needed(self) -> bool:
        if self.state.local_role == NodeRole.PRIMARY:
            return False
        time_since_heartbeat = time.time() - self._last_peer_heartbeat
        if self._last_peer_heartbeat > 0 and time_since_heartbeat > self.failover_threshold_s:
            self._log.critical(
                f"[REPLICATION] FAILOVER TRIGGERED | Peer {self.state.peer_node_id} unresponsive for {time_since_heartbeat:.1f}s (threshold: {self.failover_threshold_s}s)"
            )
            return True
        return False

    def execute_failover(self) -> NodeRole:
        if self.state.local_role == NodeRole.PRIMARY:
            return NodeRole.PRIMARY
        self.state.local_role = NodeRole.PRIMARY
        self.state.failover_count += 1
        self._last_peer_heartbeat = time.time()
        self._replication_log.append(
            {
                "action": "FAILOVER",
                "node_id": self.node_id,
                "failover_count": self.state.failover_count,
                "timestamp": time.time(),
            }
        )
        self._log.critical(
            f"[REPLICATION] FAILOVER COMPLETE | Node: {self.node_id} → PRIMARY | Failover #{self.state.failover_count}"
        )
        return NodeRole.PRIMARY

    def get_status(self) -> dict[str, Any]:
        time_since_sync = (
            time.time() - self.state.last_sync_time if self.state.last_sync_time > 0 else -1
        )
        time_since_heartbeat = (
            time.time() - self._last_peer_heartbeat if self._last_peer_heartbeat > 0 else -1
        )
        return {
            "node_id": self.node_id,
            "role": self.state.local_role.value,
            "peer_node_id": self.state.peer_node_id,
            "last_sync_time": self.state.last_sync_time,
            "time_since_sync_s": round(time_since_sync, 1),
            "last_sync_checksum": self.state.last_sync_checksum,
            "time_since_heartbeat_s": round(time_since_heartbeat, 1),
            "total_syncs": self.state.total_syncs,
            "failed_syncs": self.state.failed_syncs,
            "failover_count": self.state.failover_count,
            "failover_threshold_s": self.failover_threshold_s,
        }
