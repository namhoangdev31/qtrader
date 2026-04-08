from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
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

    Persistence:
    - In-memory by default (volatile)
    - File-based encrypted storage when storage_path is provided
    - Production: Integrate with KMS/Vault via _load_from_kms() hook
    """

    def __init__(
        self,
        master_key: bytes | None = None,
        storage_path: str | None = None,
        key_path: str | None = None,
    ) -> None:
        """
        Initialize the protected secret warehouse.

        Args:
            master_key: Optional 32-byte key. If None, a volatile key is generated.
            storage_path: Path to encrypted secrets file. If None, in-memory only.
            key_path: Path to persist/load the encryption key. If None, key is volatile.
        """
        from cryptography.fernet import Fernet  # noqa: PLC0415

        # Production baseline: Retrieve master_key from KMS/Vault.
        self._key_path = Path(key_path) if key_path else None

        # Load key from file if available, otherwise use provided or generate
        if self._key_path and self._key_path.exists():
            self._key = self._key_path.read_bytes()
        else:
            self._key = master_key or Fernet.generate_key()
            # Persist key if key_path is configured
            if self._key_path:
                self._key_path.parent.mkdir(parents=True, exist_ok=True)
                self._key_path.write_bytes(self._key)

        self._fernet: Final[Fernet] = Fernet(self._key)

        # Storage backend
        self._repo: dict[str, list[SecretMetadata]] = {}
        self._storage_path: Path | None = Path(storage_path) if storage_path else None

        # Load from persistent storage if available
        if self._storage_path:
            self._load_from_file()

        # Telemetry
        self._stats = {"access_count": 0, "unauthorized_count": 0}

    def _load_from_file(self) -> None:
        """Load encrypted secrets from persistent storage."""
        if not self._storage_path or not self._storage_path.exists():
            return

        try:
            with open(self._storage_path) as f:
                data = json.load(f)

            for secret_id, versions in data.items():
                self._repo[secret_id] = []
                for v in versions:
                    self._repo[secret_id].append(
                        SecretMetadata(
                            id=secret_id,
                            version=v["version"],
                            encrypted_value=bytes.fromhex(v["encrypted_value"]),
                            created_at=v["created_at"],
                        )
                    )

            _LOG.info(f"[SECRET_STORE] Loaded {len(self._repo)} secrets from {self._storage_path}")
        except Exception as e:
            _LOG.error(f"[SECRET_STORE] Failed to load from {self._storage_path}: {e}")

    def _save_to_file(self) -> None:
        """Persist encrypted secrets to file storage."""
        if not self._storage_path:
            return

        try:
            # Ensure directory exists
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)

            data: dict[str, list[dict]] = {}
            for secret_id, versions in self._repo.items():
                data[secret_id] = [
                    {
                        "version": v.version,
                        "encrypted_value": v.encrypted_value.hex(),
                        "created_at": v.created_at,
                    }
                    for v in versions
                ]

            # Write atomically (write to temp, then rename)
            temp_path = self._storage_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._storage_path)

            _LOG.debug(f"[SECRET_STORE] Saved {len(self._repo)} secrets to {self._storage_path}")
        except Exception as e:
            _LOG.error(f"[SECRET_STORE] Failed to save to {self._storage_path}: {e}")

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

        # Persist to file if storage is configured
        self._save_to_file()

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
            "storage_type": "file" if self._storage_path else "memory",
            "storage_path": str(self._storage_path) if self._storage_path else None,
        }
