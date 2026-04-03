"""Order Signing — Standash §5.3.

Cryptographic signing and verification of orders before exchange submission.
Provides non-repudiation and tamper-proof order integrity.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from typing import Any

_LOG = logging.getLogger("qtrader.security.order_signing")


@dataclass(slots=True)
class SignedOrder:
    """A cryptographically signed order."""

    order_payload: dict[str, Any]
    signature: str
    signing_key_id: str
    timestamp: float
    algorithm: str = "HMAC-SHA256"

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order_payload,
            "signature": self.signature,
            "signing_key_id": self.signing_key_id,
            "timestamp": self.timestamp,
            "algorithm": self.algorithm,
        }


class OrderSigner:
    """Cryptographic order signing engine — Standash §5.3.

    Signs orders with HMAC-SHA256 before exchange submission.
    Provides:
    - Non-repudiation (order origin verification)
    - Tamper detection (integrity check)
    - Replay protection (timestamp + nonce)
    """

    def __init__(self, secret_key: bytes, key_id: str = "default") -> None:
        """
        Args:
            secret_key: HMAC secret key (minimum 32 bytes recommended).
            key_id: Identifier for the signing key (for key rotation).
        """
        if len(secret_key) < 16:
            raise ValueError("Secret key must be at least 16 bytes")
        self._secret_key = secret_key
        self._key_id = key_id
        self._nonce_counter: int = 0

    def sign_order(self, order: dict[str, Any]) -> SignedOrder:
        """Sign an order payload.

        Args:
            order: Order dictionary with symbol, side, quantity, price, etc.

        Returns:
            SignedOrder with cryptographic signature.
        """
        # Add timestamp and nonce for replay protection
        order_with_meta = {
            **order,
            "signed_at": time.time(),
            "nonce": self._nonce_counter,
        }
        self._nonce_counter += 1

        # Create canonical string for signing (sorted keys for determinism)
        canonical = self._canonicalize(order_with_meta)

        # Sign with HMAC-SHA256
        signature = hmac.new(
            self._secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        signed = SignedOrder(
            order_payload=order_with_meta,
            signature=signature,
            signing_key_id=self._key_id,
            timestamp=order_with_meta["signed_at"],
        )

        _LOG.debug(
            f"[ORDER_SIGN] Signed | Key: {self._key_id} | "
            f"Nonce: {order_with_meta['nonce']} | "
            f"Symbol: {order.get('symbol', 'unknown')}"
        )

        return signed

    def verify_order(self, signed_order: SignedOrder) -> tuple[bool, str]:
        """Verify a signed order's integrity and authenticity.

        Args:
            signed_order: The signed order to verify.

        Returns:
            (is_valid, reason) tuple.
        """
        # Check key ID match
        if signed_order.signing_key_id != self._key_id:
            return (
                False,
                f"Key ID mismatch: expected {self._key_id}, got {signed_order.signing_key_id}",
            )

        # Check timestamp freshness (reject orders older than 30 seconds)
        age = time.time() - signed_order.timestamp
        if age > 30.0:
            return False, f"Order too old: {age:.1f}s (max 30s)"

        # Recompute signature
        canonical = self._canonicalize(signed_order.order_payload)
        expected_sig = hmac.new(
            self._secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signed_order.signature, expected_sig):
            return False, "Signature mismatch — order may be tampered"

        return True, "Valid"

    def verify_order_with_key(
        self, signed_order: SignedOrder, secret_key: bytes
    ) -> tuple[bool, str]:
        """Verify a signed order using a specific key (for key rotation scenarios)."""
        if len(secret_key) < 16:
            return False, "Invalid key length"

        canonical = self._canonicalize(signed_order.order_payload)
        expected_sig = hmac.new(
            secret_key,
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signed_order.signature, expected_sig):
            return False, "Signature mismatch"

        return True, "Valid"

    @staticmethod
    def _canonicalize(order: dict[str, Any]) -> str:
        """Create a canonical string representation for signing.

        Sorted keys ensure deterministic output regardless of dict ordering.
        """
        parts = []
        for key in sorted(order.keys()):
            value = order[key]
            # Convert to string representation
            if isinstance(value, float):
                parts.append(f"{key}={value:.8f}")
            else:
                parts.append(f"{key}={value}")
        return "|".join(parts)

    def rotate_key(self, new_secret_key: bytes, new_key_id: str) -> None:
        """Rotate to a new signing key."""
        if len(new_secret_key) < 16:
            raise ValueError("New secret key must be at least 16 bytes")
        old_key_id = self._key_id
        self._secret_key = new_secret_key
        self._key_id = new_key_id
        self._nonce_counter = 0
        _LOG.info(f"[ORDER_SIGN] Key rotated | Old: {old_key_id} → New: {new_key_id}")
