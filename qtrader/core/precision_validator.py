from __future__ import annotations

import decimal
from decimal import Decimal
from typing import Any, Union

from loguru import logger


class PrecisionError(Exception):
    """Exception raised when a value violates its domain-specific precision boundary."""
    pass


class PrecisionValidator:
    """
    Numerical Governance Authority.
    Ensures absolute precision consistency across system modules.
    Enforces the 'Zero Implicit Rounding' mandate.
    """

    def __init__(self, policy: dict[str, Any]) -> None:
        self.policy = policy
        self.rules = policy.get("rules", {})
        self.domains = policy.get("domains", {})

    def validate(self, value: Decimal, domain_path: str) -> None:
        """
        Validate that a value's decimal resolution does not exceed its domain's boundary.
        Args:
            value: The Decimal value to check.
            domain_path: dot-separated path (e.g. 'oms.price', 'settlement.cash').
        """
        limit = self._get_limit(domain_path)
        if limit is None:
            logger.warning(f"[PRECISION] No boundary defined for domain: {domain_path}. Bypassing.")
            return

        # Decimal exponent is -places (e.g. 0.01 has exp -2)
        exponent = value.as_tuple().exponent
        if not isinstance(exponent, int):
             # handle Infinity or NaN (should be handled elsewhere, but for safety)
             return

        current_precision = abs(exponent)

        if current_precision > limit:
            msg = (
                f"Numerical Governance Violation: Precision of {value} ({current_precision} decimals) "
                f"exceeds domain boundary for '{domain_path}' (limit: {limit}). "
                f"EXPLICIT QUANTIZATION REQUIRED."
            )
            logger.error(f"[FATAL] {msg}")
            if self.rules.get("fail_on_precision_mismatch", True):
                raise PrecisionError(msg)

    def _get_limit(self, path: str) -> int | None:
        """Heuristically retrieve a precision limit from the hierarchical policy."""
        parts = path.split(".")
        current = self.domains
        for p in parts:
            if isinstance(current, dict) and p in current:
                current = current[p]
            else:
                return None
        
        return current if isinstance(current, int) else None

    @staticmethod
    def get_decimals(value: Decimal) -> int:
        """Helper to get the number of decimal places in a value (normalized)."""
        # normalize() removes trailing zeros but preserves the value
        # e.g. 1.100 becomes 1.1 with exp -1
        normalized = value.normalize()
        exp = normalized.as_tuple().exponent
        return abs(exp) if isinstance(exp, int) else 0


# Initialization Example (To be integrated into math_authority)
# For now, we define a prototype validator
prototype_policy = {
    "domains": {
        "pnl_engine": 18,
        "nav_engine": 12,
        "risk_engine": 12,
        "oms": {"price": 8, "quantity": 6},
        "settlement": {"cash": 2, "fees": 10, "notional": 2}
    },
    "rules": {
        "fail_on_precision_mismatch": True
    }
}
math_validator = PrecisionValidator(prototype_policy)
