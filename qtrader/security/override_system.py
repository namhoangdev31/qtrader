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
    user_id: str
    role: Role
    timestamp: float


@dataclass(slots=True)
class OverrideRequest:
    request_id: str
    requester_id: str
    action: str
    reason: str
    requested_at: float
    approvals: list[OverrideApproval] = field(default_factory=list)
    authorized: bool = False


class HumanOverrideEnforcer:
    OVERRIDE_VALIDITY_S: Final[int] = 300

    def __init__(self, mfa_engine: MultiFactorAuthenticator) -> None:
        self._mfa = mfa_engine
        self._requests: dict[str, OverrideRequest] = {}
        self._stats = {"overrides_granted": 0, "overrides_rejected": 0}

    def request_override(self, user_id: str, action: str, reason: str) -> str:
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
        if request_id not in self._requests:
            return False
        request = self._requests[request_id]
        pwd = f"SECURE_PWD_{approver_id}"
        mfa_status = self._mfa.verify(approver_id, pwd, mfa_token, ip_addr, {ip_addr})
        if not mfa_status.verified:
            _LOG.warning(f"[OVERRIDE] SIGNATURE_DENY | Req: {request_id} | MFA FAIL")
            return False
        if approver_id == request.requester_id:
            _LOG.warning(f"[OVERRIDE] SOD_VIOLATION | Req: {request_id} | Self-Approval Denied")
            return False
        if any(a.user_id == approver_id for a in request.approvals):
            _LOG.warning(f"[OVERRIDE] DUPLICATE_SIGN_DENY | Req: {request_id} | {approver_id}")
            return False
        approval = OverrideApproval(approver_id, approver_role, time.time())
        request.approvals.append(approval)
        _LOG.info(f"[OVERRIDE] SIGNED | Req: {request_id} | User: {approver_id}")
        return True

    def authorize(self, request_id: str) -> bool:
        if request_id not in self._requests:
            return False
        request = self._requests[request_id]
        if time.time() - request.requested_at > self.OVERRIDE_VALIDITY_S:
            _LOG.error(f"[OVERRIDE] EXPIRED | Req: {request_id}")
            self._stats["overrides_rejected"] += 1
            return False
        if len(request.approvals) < 2:
            _LOG.warning(f"[OVERRIDE] QUORUM_MISSING | Req: {request_id}")
            return False
        (role1, role2) = (request.approvals[0].role, request.approvals[1].role)
        if role1 == role2:
            _LOG.error(f"[OVERRIDE] ROLE_OVERLAP_VIOLATION | Req: {request_id} | {role1.name}")
            self._stats["overrides_rejected"] += 1
            return False
        request.authorized = True
        self._stats["overrides_granted"] += 1
        _LOG.info(
            f"[OVERRIDE] AUTHORIZED | Req: {request_id} | Approvers: {request.approvals[0].user_id}, {request.approvals[1].user_id}"
        )
        return True

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "REPORT",
            "overrides_granted": self._stats["overrides_granted"],
            "overrides_rejected": self._stats["overrides_rejected"],
        }
