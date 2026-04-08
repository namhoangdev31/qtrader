"""Token Bucket Rate Limiter for Python-side safety checks."""

import time
import asyncio
from threading import Lock

class TokenBucketRateLimiter:
    """
    Thread-safe Token Bucket Rate Limiter to enforce account-level or system-level limits.
    Can be used in both async and sync contexts.
    """
    def __init__(self, capacity: float, refill_rate: float):
        """
        Args:
            capacity: Maximum number of tokens the bucket can hold.
            refill_rate: Number of tokens added per second.
        """
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill_time = time.monotonic()
        self._lock = Lock()

    def consume(self, amount: float = 1.0) -> bool:
        """
        Try to consume tokens.
        Returns: True if tokens were consumed, False otherwise.
        """
        with self._lock:
            self._refill()
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    async def wait_and_consume(self, amount: float = 1.0):
        """
        Wait until enough tokens are available and then consume them.
        """
        while not self.consume(amount):
            # Sleep for a short duration before retrying
            await asyncio.sleep(0.1 / self.refill_rate)

    def _refill(self):
        """Internal refill logic based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill_time = now

    def get_token_count(self) -> float:
        """Get current number of available tokens."""
        with self._lock:
            self._refill()
            return self.tokens
