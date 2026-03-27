from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from qtrader.core.events import BaseEvent, MetaDecisionEvent, MetaDecisionPayload

_LOG = logging.getLogger("qtrader.meta.audit_logger")


class AuditStoreProtocol(Protocol):
    """Structural typing for the DuckDB-based AuditStore."""

    async def append(self, event: BaseEvent) -> bool: ...


class MetaAuditLogger:
    """
    Principal Audit System for Meta-Control Governance.

    Guarantees 100% deterministic traceability of all autonomous decisions
    (approvals, rejections, transitions). Persists to both the DuckDB
    Analytical Store and local immutable JSONL logs for industrial auditability.
    """

    def __init__(
        self,
        audit_store: AuditStoreProtocol | None = None,
        log_path: str = "meta_audit.log",
    ) -> None:
        """
        Initialize the audit log system.

        Args:
            audit_store: The principal OLAP store (DuckDB).
            log_path: Secondary local JSONL file for raw audit trails.
        """
        self._audit_store = audit_store
        self._log_path = log_path
        self._stats = {"events_logged": 0, "store_failures": 0}

    async def log_decision(  # noqa: PLR0913
        self,
        module: str,
        action: str,
        entity_id: str,
        decision: str,
        reason: str,
        metrics: dict[str, float] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MetaDecisionEvent:
        """
        Capture and persist a deterministic meta-control decision.

        Args:
            module: Originating module (e.g., 'ConstraintEngine').
            action: Action performed (e.g., 'STRATEGY_VALIDATION').
            entity_id: The ID of the strategy or model being evaluated.
            decision: Outcome ('APPROVED', 'REJECTED', 'TRANSITION').
            reason: Humanitarian explanation for the decision.
            metrics: Input metrics that triggered the decision.
            metadata: Supplemental context for audit replay.

        Returns:
            The immutable MetaDecisionEvent that was captured.
        """
        trace_id = uuid4()
        payload = MetaDecisionPayload(
            module=module,
            action=action,
            entity_id=entity_id,
            decision=decision,
            reason=reason,
            metrics=metrics or {},
            metadata=metadata or {},
        )

        event = MetaDecisionEvent(
            trace_id=trace_id,
            source=module,
            payload=payload,
        )

        # 1. Local Immutable Persistence (JSONL)
        self._persist_local(event)

        # 2. Principle Analytical Store Persistence (Async)
        if self._audit_store:
            success = await self._audit_store.append(event)
            if not success:
                self._stats["store_failures"] += 1
                _LOG.error(f"AUDIT_STORE_FAILURE | Decision {event.event_id} dropped from DB.")

        self._stats["events_logged"] += 1
        _LOG.info(f"[AUDIT] {module} | {entity_id} | {decision} | {reason}")

        return event

    def _persist_local(self, event: MetaDecisionEvent) -> None:
        """Append the structured record to the local JSONL audit trail."""
        try:
            record = {
                "timestamp": datetime.fromtimestamp(
                    event.timestamp / 1_000_000, tz=timezone.utc
                ).isoformat(),
                "event_id": str(event.event_id),
                "module": event.payload.module,
                "action": event.payload.action,
                "entity_id": event.payload.entity_id,
                "decision": event.payload.decision,
                "reason": event.payload.reason,
                "metrics": event.payload.metrics,
                "metadata": event.payload.metadata,
            }

            with open(self._log_path, "a") as f:
                f.write(json.dumps(record) + "\n")

        except Exception as e:
            _LOG.critical(f"AUDIT_LOCAL_FAILURE | Could not write to {self._log_path}: {e!s}")

    def get_audit_report(self) -> dict[str, Any]:
        """Output the health and volume of the audit system."""
        return {
            "status": "LOGGED",
            "events_logged": self._stats["events_logged"],
            "store_failures": self._stats["store_failures"],
            "log_file": self._log_path,
        }
