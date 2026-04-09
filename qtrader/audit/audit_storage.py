from __future__ import annotations
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Final

_LOG = logging.getLogger("qtrader.audit.audit_storage")
RETENTION_PERIOD_S: Final[int] = 157680000


@dataclass(slots=True)
class AuditRecord:
    record_id: str
    topic: str
    payload_json: str
    timestamp: float
    expiry_ts: float
    fingerprint: str


class AuditStorageManager:
    def __init__(self) -> None:
        self._storage: dict[str, AuditRecord] = {}
        self._stats = {"stored_count": 0, "tamper_verifications": 0}

    def append(self, topic: str, payload: dict[str, Any]) -> str:
        s_payload = json.dumps(payload, sort_keys=True)
        fingerprint = hashlib.sha256(f"{topic}:{s_payload}".encode()).hexdigest()
        now = time.time()
        record_id = hashlib.sha256(f"{topic}:{fingerprint}:{now}".encode()).hexdigest()[:16]
        record = AuditRecord(
            record_id=record_id,
            topic=topic,
            payload_json=s_payload,
            timestamp=now,
            expiry_ts=now + RETENTION_PERIOD_S,
            fingerprint=fingerprint,
        )
        if record_id in self._storage:
            raise RuntimeError(f"[AUDIT_STORAGE] CRITICAL | Record ID collision: {record_id}")
        self._storage[record_id] = record
        self._stats["stored_count"] += 1
        _LOG.info(f"[AUDIT_STORAGE] RECORD_COMMITTED | ID: {record_id} | Topic: {topic}")
        return record_id

    def verify_integrity(self, record_id: str) -> bool:
        record = self._storage.get(record_id)
        if not record:
            return False
        current_hash = hashlib.sha256(f"{record.topic}:{record.payload_json}".encode()).hexdigest()
        is_valid = current_hash == record.fingerprint
        if is_valid:
            self._stats["tamper_verifications"] += 1
        else:
            _LOG.error(f"[AUDIT_STORAGE] FORENSIC_ALERT | Tamper detected for ID: {record_id}")
        return is_valid

    def query_range(self, topic: str, start_ts: float, end_ts: float) -> list[dict[str, Any]]:
        results = []
        for r in self._storage.values():
            if r.topic == topic and start_ts <= r.timestamp <= end_ts:
                results.append(
                    {
                        "record_id": r.record_id,
                        "payload": json.loads(r.payload_json),
                        "timestamp": r.timestamp,
                        "fingerprint": r.fingerprint,
                    }
                )
        return results

    def perform_retention_maintenance(self) -> int:
        now = time.time()
        to_purge = [rid for (rid, r) in self._storage.items() if now >= r.expiry_ts]
        for rid in to_purge:
            del self._storage[rid]
        return len(to_purge)

    def get_audit_report(self) -> dict[str, Any]:
        return {
            "status": "STORED",
            "total_records": self._stats["stored_count"],
            "integrity_verifications": self._stats["tamper_verifications"],
            "retention_period_years": 5,
        }
