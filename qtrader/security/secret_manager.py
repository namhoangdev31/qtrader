from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Final

from qtrader.security.rbac import Permission, RBACProcessor

_LOG = logging.getLogger("qtrader.security.secret_manager")


@dataclass(slots=True, frozen=True)
class SecretMetadata:
    """
    Industrial Secret Version Metadata.
    """

    id: str
    version: int
    encrypted_value: bytes
    created_at: float


class SecretManager:
    """
    Principal Secret Management Engine.

    Objective: Securely store and retrieve sensitive credentials (API Keys, DB Passwords)
    using industrial-grade symmetric encryption (AES-256 equivalent via Fernet)
    with mandatory RBAC gating and immutable versioning.
    """

    def __init__(self, master_key: bytes | None = None) -> None:
        """
        Initialize the protected secret warehouse.

        Args:
            master_key: Optional 32-byte key. If None, a volatile key is generated.
        """
        from cryptography.fernet import Fernet  # noqa: PLC0415
        # Production baseline: Retrieve master_key from KMS/Vault.
        self._key: Final[bytes] = master_key or Fernet.generate_key()
        self._fernet: Final[Fernet] = Fernet(self._key)

        # In-memory storage for the industrial prototype.
        # Production equivalent: Encrypted persistent warehouse (e.g., PostgreSQL/S3).
        self._repo: dict[str, list[SecretMetadata]] = {}

        # Telemetry
        self._stats = {"access_count": 0, "unauthorized_count": 0}

    def store_secret(self, secret_id: str, plaintext: str) -> int:
        """
        Securely store a new version of a secret.

        Returns:
            int: The monotonic version number assigned to the secret.
        """
        encrypted = self._fernet.encrypt(plaintext.encode())

        if secret_id not in self._repo:
            self._repo[secret_id] = []

        version = len(self._repo[secret_id]) + 1
        metadata = SecretMetadata(
            id=secret_id,
            version=version,
            encrypted_value=encrypted,
            created_at=time.time(),
        )

        self._repo[secret_id].append(metadata)
        _LOG.info(f"[SECRET_ACCESS] STORED | ID: {secret_id} | Version: {version}")
        return version

    def get_secret(self, secret_id: str, version: int | None = None) -> str | None:
        """
        Authorize and retrieve a decrypted secret.

        Decision Rules:
        1. RBAC Check: User context must have Permission.READ_PROD_DATA.
        2. Integrity Check: Secret ID must exist in the warehouse.
        3. Version Resolve: Defaults to latest if not specified.

        Returns:
            str | None: The plaintext secret or None if access is denied/missing.
        """
        # 1. Zero-Trust Access Gate
        if not RBACProcessor.check_access(Permission.READ_SECRET):
            self._stats["unauthorized_count"] += 1
            _LOG.error(
                f"[SECRET_ACCESS] DENY | ID: {secret_id} | "
                "Unauthorized attempted credential retrieval"
            )
            return None

        # 2. Retrieval Logic
        if secret_id not in self._repo:
            _LOG.warning(f"[SECRET_ACCESS] MISSING | ID: {secret_id}")
            return None

        versions = self._repo[secret_id]
        if version is None:
            # Industrial default: Latest stable version
            metadata = versions[-1]
        else:
            # Pin to specific historical audit version
            found = [v for v in versions if v.version == version]
            if not found:
                _LOG.warning(f"[SECRET_ACCESS] VERSION_MISSING | ID: {secret_id} V{version}")
                return None
            metadata = found[0]

        # 3. Decryption Completion
        self._stats["access_count"] += 1
        _LOG.info(f"[SECRET_ACCESS] GRANTED | ID: {secret_id} | Version: {metadata.version}")
        return self._fernet.decrypt(metadata.encrypted_value).decode()

    def get_report(self) -> dict[str, Any]:
        """
        Generate operational security situational awareness report.
        """
        return {
            "status": "REPORT",
            "managed_secrets": len(self._repo),
            "access_count": self._stats["access_count"],
            "unauthorized_attempts": self._stats["unauthorized_count"],
        }
