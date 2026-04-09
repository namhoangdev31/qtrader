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
    id: str
    version: int
    encrypted_value: bytes
    created_at: float


class SecretManager:
    def __init__(
        self,
        master_key: bytes | None = None,
        storage_path: str | None = None,
        key_path: str | None = None,
    ) -> None:
        from cryptography.fernet import Fernet

        self._key_path = Path(key_path) if key_path else None
        if self._key_path and self._key_path.exists():
            self._key = self._key_path.read_bytes()
        else:
            self._key = master_key or Fernet.generate_key()
            if self._key_path:
                self._key_path.parent.mkdir(parents=True, exist_ok=True)
                self._key_path.write_bytes(self._key)
        self._fernet: Final[Fernet] = Fernet(self._key)
        self._repo: dict[str, list[SecretMetadata]] = {}
        self._storage_path: Path | None = Path(storage_path) if storage_path else None
        if self._storage_path:
            self._load_from_file()
        self._stats = {"access_count": 0, "unauthorized_count": 0}

    def _load_from_file(self) -> None:
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
        if not self._storage_path:
            return
        try:
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
            temp_path = self._storage_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self._storage_path)
            _LOG.debug(f"[SECRET_STORE] Saved {len(self._repo)} secrets to {self._storage_path}")
        except Exception as e:
            _LOG.error(f"[SECRET_STORE] Failed to save to {self._storage_path}: {e}")

    def store_secret(self, secret_id: str, plaintext: str) -> int:
        encrypted = self._fernet.encrypt(plaintext.encode())
        if secret_id not in self._repo:
            self._repo[secret_id] = []
        version = len(self._repo[secret_id]) + 1
        metadata = SecretMetadata(
            id=secret_id, version=version, encrypted_value=encrypted, created_at=time.time()
        )
        self._repo[secret_id].append(metadata)
        self._save_to_file()
        _LOG.info(f"[SECRET_ACCESS] STORED | ID: {secret_id} | Version: {version}")
        return version

    def get_secret(self, secret_id: str, version: int | None = None) -> str | None:
        if not RBACProcessor.check_access(Permission.READ_SECRET):
            self._stats["unauthorized_count"] += 1
            _LOG.error(
                f"[SECRET_ACCESS] DENY | ID: {secret_id} | Unauthorized attempted credential retrieval"
            )
            return None
        if secret_id not in self._repo:
            _LOG.warning(f"[SECRET_ACCESS] MISSING | ID: {secret_id}")
            return None
        versions = self._repo[secret_id]
        if version is None:
            metadata = versions[-1]
        else:
            found = [v for v in versions if v.version == version]
            if not found:
                _LOG.warning(f"[SECRET_ACCESS] VERSION_MISSING | ID: {secret_id} V{version}")
                return None
            metadata = found[0]
        self._stats["access_count"] += 1
        _LOG.info(f"[SECRET_ACCESS] GRANTED | ID: {secret_id} | Version: {metadata.version}")
        return self._fernet.decrypt(metadata.encrypted_value).decode()

    def get_report(self) -> dict[str, Any]:
        return {
            "status": "REPORT",
            "managed_secrets": len(self._repo),
            "access_count": self._stats["access_count"],
            "unauthorized_attempts": self._stats["unauthorized_count"],
            "storage_type": "file" if self._storage_path else "memory",
            "storage_path": str(self._storage_path) if self._storage_path else None,
        }
