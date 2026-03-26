import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class KeyMetadata:
    """Metadata for an API key instance."""

    key: str
    created_at: datetime
    is_revoked: bool = False


class KeyRotationManager:
    """
    Manages the lifecycle of API keys, including generation and rotation.
    Keys automatically expire after a configurable period.
    """

    def __init__(self, rotation_days: int = 30) -> None:
        """
        Args:
            rotation_days: Number of days before a key expires.
        """
        self.rotation_days = rotation_days
        self._keys: dict[str, KeyMetadata] = {}

    def generate_key(self) -> str:
        """
        Generate a new unique API key.

        Returns:
            str: The generated key.
        """
        key = secrets.token_urlsafe(32)
        self._keys[key] = KeyMetadata(key=key, created_at=datetime.now())
        return key

    def is_valid(self, key: str) -> bool:
        """
        Check if a key is currently valid (exists, not revoked, not expired).

        Args:
            key: The key to validate.

        Returns:
            bool: True if valid, False otherwise.
        """
        metadata = self._keys.get(key)
        if not metadata or metadata.is_revoked:
            return False

        expiry_time = metadata.created_at + timedelta(days=self.rotation_days)
        if datetime.now() > expiry_time:
            metadata.is_revoked = True  # Auto-revoke upon expiry detection
            return False

        return True

    def rotate_key(self, old_key: str) -> str | None:
        """
        Revoke an old key and generate a new one.

        Args:
            old_key: The existing key to rotate.

        Returns:
            Optional[str]: The new key if successful, None if old_key is invalid.
        """
        if old_key not in self._keys:
            return None

        self.revoke_key(old_key)
        return self.generate_key()

    def revoke_key(self, key: str) -> bool:
        """
        Permanently revoke an API key.

        Args:
            key: The key to revoke.

        Returns:
            bool: True if revoked successfully, False if not found.
        """
        if key in self._keys:
            self._keys[key].is_revoked = True
            return True
        return False
