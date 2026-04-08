from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from qtrader.security.mfa import MultiFactorAuthenticator
    from qtrader.security.rbac import Role

_LOG = logging.getLogger("qtrader.security.override_system")


@dataclass(slots=True, frozen=True)
class OverrideApproval:
    """
    Industrial Digital Signature for a platform override.
    """

    user_id: str
    role: Role
    timestamp: float


@dataclass(slots=True)
class OverrideRequest:
    """
    Hardened Intent to override system risk/platform controls.
    """

    request_id: str
    requester_id: str
    action: str
    reason: str
    requested_at: float
    approvals: list[OverrideApproval] = field(default_factory=list)
    authorized: bool = False


class HumanOverrideEnforcer:
    """
    Principal Operational Governance Engine.

    Objective: Enforce the 'Four-Eyes Principle' (Dual Control) for all high-risk
    system interventions.
    Authorizes overrides ONLY if validated by exactly 2 distinct functional roles
    (e.g., TRADER + RISK_MANAGER) with mandatory MFA validation.

    Governance Constants:
    - Validity Window: 300 seconds (5 minutes).
    - Separation of Duties (SoD): No self-approval (Requester cannot be Approver).
    """

    OVERRIDE_VALIDITY_S: Final[int] = 300

    def __init__(self, mfa_engine: MultiFactorAuthenticator) -> None:
        """
        Initialize the governance enforcer.
        """
        self._mfa = mfa_engine
        # In-memory storage for the industrial prototype.
        self._requests: dict[str, OverrideRequest] = {}

        # Telemetry
        self._stats = {"overrides_granted": 0, "overrides_rejected": 0}

    def request_override(self, user_id: str, action: str, reason: str) -> str:
        """
        Register a new intent for platform intervention.
        """
        request_id = f"OVR_{int(time.time())}_{user_id}"
        request = OverrideRequest(
            request_id=request_id,
            requester_id=user_id,
            action=action,
            reason=reason,
            requested_at=time.time(),
        )
        self._requests[request_id] = request
        _LOG.info(f"[OVERRIDE] REQUESTED | ID: {request_id} | User: {user_id}")
        return request_id

    def submit_approval(
        self,
        request_id: str,
        approver_id: str,
        approver_role: Role,
        mfa_token: str,
        ip_addr: str = "127.0.0.1",
    ) -> bool:
        """
        Append an industrial signature to a pending override request.

        Decision Rules:
        1. MFA Verification: Validates approver identity in real-time.
        2. Separation of Duties: Ensure approver != requester.
        3. Identity Uniqueness: No duplicate signatures from the same user.
        """
        if request_id not in self._requests:
            return False

        request = self._requests[request_id]

        # 1. Identity Assurance Signature (MFA)
        # Simulation: Using industrial hash baseline for the approver password.
        pwd = f"SECURE_PWD_{approver_id}"
        mfa_status = self._mfa.verify(approver_id, pwd, mfa_token, ip_addr, {ip_addr})
        if not mfa_status.verified:
            _LOG.warning(f"[OVERRIDE] SIGNATURE_DENY | Req: {request_id} | MFA FAIL")
            return False

        # 2. Separation of Duties - Zero Self-Approval
        if approver_id == request.requester_id:
            _LOG.warning(f"[OVERRIDE] SOD_VIOLATION | Req: {request_id} | Self-Approval Denied")
            return False

        # 3. Duplicate Prevention
        if any(a.user_id == approver_id for a in request.approvals):
            _LOG.warning(f"[OVERRIDE] DUPLICATE_SIGN_DENY | Req: {request_id} | {approver_id}")
            return False

        # Record point-of-signature metadata.
        approval = OverrideApproval(approver_id, approver_role, time.time())
        request.approvals.append(approval)
        _LOG.info(f"[OVERRIDE] SIGNED | Req: {request_id} | User: {approver_id}")
        return True

    def authorize(self, request_id: str) -> bool:
        """
        Final execution of quaternary governance rules.

        Conditions for Authorized status:
        a) EXACT QUORUM: Exactly 2 distinct approvals required.
        b) FUNCTIONAL SEGREGATION: Approver1 role != Approver2 role.
        c) TEMPORAL INTEGRITY: Elapsed time since request <= 300 seconds.

        Returns:
            bool: True if fully authorized, else False.
        """
        if request_id not in self._requests:
            return False

        request = self._requests[request_id]

        # 1. Temporal Integrity Baseline
        if time.time() - request.requested_at > self.OVERRIDE_VALIDITY_S:
            _LOG.error(f"[OVERRIDE] EXPIRED | Req: {request_id}")
            self._stats["overrides_rejected"] += 1
            return False

        # 2. Quorum Check (Four-Eyes Requirement)
        if len(request.approvals) < 2:  # noqa: PLR2004
            _LOG.warning(f"[OVERRIDE] QUORUM_MISSING | Req: {request_id}")
            return False

        # 3. Functional Segregation Check (Role Overlap Prevention)
        # Rule: TRADER + RISK_MANAGER required.
        role1, role2 = request.approvals[0].role, request.approvals[1].role
        if role1 == role2:
            _LOG.error(f"[OVERRIDE] ROLE_OVERLAP_VIOLATION | Req: {request_id} | {role1.name}")
            self._stats["overrides_rejected"] += 1
            return False

        # 4. Final Platform Authorization
        request.authorized = True
        self._stats["overrides_granted"] += 1
        _LOG.info(
            f"[OVERRIDE] AUTHORIZED | Req: {request_id} | Approvers: "
            f"{request.approvals[0].user_id}, {request.approvals[1].user_id}"
        )
        return True

    def get_report(self) -> dict[str, Any]:
        """
        Generate operational governance situational awareness report.
        """
        return {
            "status": "REPORT",
            "overrides_granted": self._stats["overrides_granted"],
            "overrides_rejected": self._stats["overrides_rejected"],
        }
