import asyncio
import time
from threading import Lock


class TokenBucketRateLimiter:
    def __init__(self, capacity: float, refill_rate: float):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill_time = time.monotonic()
        self._lock = Lock()

    def consume(self, amount: float = 1.0) -> bool:
        with self._lock:
            self._refill()
            if self.tokens >= amount:
                self.tokens -= amount
                return True
            return False

    async def wait_and_consume(self, amount: float = 1.0):
        while not self.consume(amount):
            await asyncio.sleep(0.1 / self.refill_rate)

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill_time
        new_tokens = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill_time = now

    def get_token_count(self) -> float:
        with self._lock:
            self._refill()
            return self.tokens
