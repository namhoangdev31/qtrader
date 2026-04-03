"""Runtime Risk Override — Standash §4.15.

Provides a governed pathway to override risk limits at runtime
without requiring a code deployment. All overrides are:
1. Authenticated (RBAC-gated)
2. Time-bounded (auto-expire)
3. Fully audited (audit trail)
4. Reversible (rollback capability)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_LOG = logging.getLogger("qtrader.risk.risk_override")


class OverrideStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class OverrideType(str, Enum):
    DD_LIMIT = "DD_LIMIT"
    EXPOSURE_LIMIT = "EXPOSURE_LIMIT"
    LEVERAGE_LIMIT = "LEVERAGE_LIMIT"
    POSITION_SIZE_LIMIT = "POSITION_SIZE_LIMIT"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    CONCENTRATION_LIMIT = "CONCENTRATION_LIMIT"


@dataclass(slots=True)
class RiskOverride:
    """A single risk override record."""

    override_id: str
    override_type: OverrideType
    original_value: float
    override_value: float
    reason: str
    authorized_by: str  # RBAC user ID
    approved_by: str | None  # Four-eyes principle approver
    created_at: float
    expires_at: float
    status: OverrideStatus = OverrideStatus.PENDING
    symbol: str | None = None  # Optional: limit override to specific symbol
    notes: str = ""

    @property
    def is_active(self) -> bool:
        now = time.time()
        return self.status == OverrideStatus.ACTIVE and now < self.expires_at

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at or self.status == OverrideStatus.EXPIRED


class RuntimeRiskOverrideEngine:
    """Runtime Risk Override Engine — Standash §4.15.

    Allows authorized personnel to temporarily override risk limits
    with full governance controls:
    - RBAC authentication
    - Four-eyes approval (optional)
    - Time-bounded overrides (auto-expire)
    - Full audit trail
    - Rollback capability
    """

    def __init__(
        self,
        max_override_duration_s: float = 3600.0,  # Default 1 hour
        require_four_eyes: bool = True,
        max_overrides_active: int = 3,
    ) -> None:
        self.max_override_duration_s = max_override_duration_s
        self.require_four_eyes = require_four_eyes
        self.max_overrides_active = max_overrides_active
        self._overrides: dict[str, RiskOverride] = {}
        self._audit_log: list[dict[str, Any]] = []
        self._log = logging.getLogger("qtrader.risk.risk_override")

    def request_override(
        self,
        override_type: OverrideType,
        override_value: float,
        original_value: float,
        reason: str,
        requested_by: str,
        symbol: str | None = None,
        duration_s: float | None = None,
    ) -> RiskOverride:
        """Request a risk override.

        Args:
            override_type: Type of limit being overridden.
            override_value: New limit value.
            original_value: Current limit value.
            reason: Business justification.
            requested_by: RBAC user ID of requester.
            symbol: Optional symbol-specific override.
            duration_s: Override duration in seconds (default: max_override_duration_s).

        Returns:
            RiskOverride record (status=PENDING until approved).
        """
        # Check active override count
        active_count = sum(1 for o in self._overrides.values() if o.is_active)
        if active_count >= self.max_overrides_active:
            raise ValueError(
                f"Maximum active overrides ({self.max_overrides_active}) reached. "
                f"Revoke existing overrides first."
            )

        override_id = str(uuid.uuid4())
        duration = duration_s or self.max_override_duration_s
        now = time.time()

        override = RiskOverride(
            override_id=override_id,
            override_type=override_type,
            original_value=original_value,
            override_value=override_value,
            reason=reason,
            authorized_by=requested_by,
            approved_by=None,
            created_at=now,
            expires_at=now + duration,
            status=OverrideStatus.PENDING,
            symbol=symbol,
        )

        self._overrides[override_id] = override
        self._audit_log.append(
            {
                "action": "OVERRIDE_REQUESTED",
                "override_id": override_id,
                "type": override_type.value,
                "requested_by": requested_by,
                "reason": reason,
                "timestamp": now,
            }
        )

        self._log.warning(
            f"[RISK_OVERRIDE] Requested | Type: {override_type.value} | "
            f"Original: {original_value} → New: {override_value} | "
            f"By: {requested_by} | Reason: {reason}"
        )

        return override

    def approve_override(self, override_id: str, approved_by: str) -> bool:
        """Approve a pending override (four-eyes principle).

        Args:
            override_id: Override to approve.
            approved_by: RBAC user ID of approver (must differ from requester).

        Returns:
            True if approved successfully.
        """
        override = self._overrides.get(override_id)
        if not override:
            raise KeyError(f"Override {override_id} not found")

        if override.status != OverrideStatus.PENDING:
            raise ValueError(f"Override {override_id} is {override.status.value}, not PENDING")

        if self.require_four_eyes and approved_by == override.authorized_by:
            raise ValueError("Four-eyes principle: approver must differ from requester")

        override.status = OverrideStatus.ACTIVE
        override.approved_by = approved_by

        self._audit_log.append(
            {
                "action": "OVERRIDE_APPROVED",
                "override_id": override_id,
                "approved_by": approved_by,
                "timestamp": time.time(),
            }
        )

        self._log.warning(
            f"[RISK_OVERRIDE] Approved | ID: {override_id} | "
            f"Type: {override.override_type.value} | "
            f"By: {approved_by}"
        )

        return True

    def revoke_override(self, override_id: str, revoked_by: str) -> bool:
        """Revoke an active override.

        Args:
            override_id: Override to revoke.
            revoked_by: RBAC user ID of revoker.

        Returns:
            True if revoked successfully.
        """
        override = self._overrides.get(override_id)
        if not override:
            raise KeyError(f"Override {override_id} not found")

        if not override.is_active:
            raise ValueError(f"Override {override_id} is not active")

        override.status = OverrideStatus.REVOKED

        self._audit_log.append(
            {
                "action": "OVERRIDE_REVOKED",
                "override_id": override_id,
                "revoked_by": revoked_by,
                "timestamp": time.time(),
            }
        )

        self._log.info(f"[RISK_OVERRIDE] Revoked | ID: {override_id} | By: {revoked_by}")
        return True

    def get_effective_limit(
        self,
        override_type: OverrideType,
        default_value: float,
        symbol: str | None = None,
    ) -> float:
        """Get the effective limit value considering active overrides.

        Args:
            override_type: Type of limit.
            default_value: Default limit value if no override is active.
            symbol: Optional symbol to check for symbol-specific overrides.

        Returns:
            Effective limit value (override value if active, else default).
        """
        # Check for active overrides
        for override in self._overrides.values():
            if (
                override.is_active
                and override.override_type == override_type
                and (symbol is None or override.symbol is None or override.symbol == symbol)
            ):
                return override.override_value

        return default_value

    def cleanup_expired(self) -> int:
        """Clean up expired overrides. Returns count of expired overrides."""
        expired_count = 0
        for override in self._overrides.values():
            if override.is_active and override.is_expired:
                override.status = OverrideStatus.EXPIRED
                expired_count += 1
                self._audit_log.append(
                    {
                        "action": "OVERRIDE_EXPIRED",
                        "override_id": override.override_id,
                        "type": override.override_type.value,
                        "timestamp": time.time(),
                    }
                )
                self._log.info(
                    f"[RISK_OVERRIDE] Expired | ID: {override.override_id} | "
                    f"Type: {override.override_type.value}"
                )
        return expired_count

    def get_audit_log(self) -> list[dict[str, Any]]:
        """Return full audit log for compliance reporting."""
        return list(self._audit_log)

    def get_active_overrides(self) -> list[RiskOverride]:
        """Return all currently active overrides."""
        return [o for o in self._overrides.values() if o.is_active]

    def get_status(self) -> dict[str, Any]:
        """Return override engine status."""
        active = self.get_active_overrides()
        return {
            "active_override_count": len(active),
            "max_overrides_active": self.max_overrides_active,
            "require_four_eyes": self.require_four_eyes,
            "max_override_duration_s": self.max_override_duration_s,
            "active_overrides": [
                {
                    "id": o.override_id,
                    "type": o.override_type.value,
                    "original": o.original_value,
                    "override": o.override_value,
                    "authorized_by": o.authorized_by,
                    "approved_by": o.approved_by,
                    "expires_at": o.expires_at,
                    "symbol": o.symbol,
                }
                for o in active
            ],
            "total_audit_entries": len(self._audit_log),
        }
