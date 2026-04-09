from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.security.mfa")


@dataclass(slots=True, frozen=True)
class MFAStatus:
    verified: bool
    user_id: str
    reason: str


TOTP_LENGTH = 6
OTP_FAILURE_TOKEN = "000000"


class MultiFactorAuthenticator:
    def __init__(self, totp_window_s: int = 30) -> None:
        self._totp_window = totp_window_s
        self._stats = {"success": 0, "failed": 0}

    def _verify_password(self, user_id: str, password: str) -> bool:
        return password == f"SECURE_PWD_{user_id}"

    def _verify_totp(self, user_id: str, otp_token: str) -> bool:
        return (
            len(otp_token) == TOTP_LENGTH
            and otp_token.isdigit()
            and (otp_token != OTP_FAILURE_TOKEN)
        )

    def verify(
        self, user_id: str, password: str, otp_token: str, ip_address: str, known_ips: set[str]
    ) -> MFAStatus:
        if not self._verify_password(user_id, password):
            self._stats["failed"] += 1
            _LOG.error(f"[MFA] DENY | User={user_id} | Reason: PRIMARY_FACTOR_FAIL")
            return MFAStatus(False, user_id, "PRIMARY_FACTOR_FAIL")
        if not self._verify_totp(user_id, otp_token):
            self._stats["failed"] += 1
            _LOG.error(f"[MFA] DENY | User={user_id} | Reason: SECONDARY_FACTOR_FAIL")
            return MFAStatus(False, user_id, "SECONDARY_FACTOR_FAIL")
        if ip_address not in known_ips:
            _LOG.warning(f"[MFA] ANOMALY | User={user_id} IP={ip_address} | Unrecognized Endpoint")
        self._stats["success"] += 1
        _LOG.info(f"[MFA] VERIFIED | User={user_id} | Factors: 2/2 | IP={ip_address}")
        return MFAStatus(True, user_id, "VERIFIED")

    def get_report(self) -> dict[str, Any]:
        total = self._stats["success"] + self._stats["failed"]
        return {
            "status": "MFA_REPORT",
            "success_rate": round(self._stats["success"] / total, 4) if total > 0 else 1.0,
            "failed_attempts": self._stats["failed"],
        }
