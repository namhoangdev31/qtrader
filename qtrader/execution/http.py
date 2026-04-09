import asyncio
from dataclasses import dataclass
from typing import Any
import aiohttp


@dataclass(frozen=True)
class RetryConfig:
    request_timeout_s: float = 10.0
    max_retries: int = 3
    retry_backoff_ms: int = 200


def _is_retryable_status(status: int) -> bool:
    return 500 <= status <= 599


async def request_json(
    *,
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    retry: RetryConfig = RetryConfig(),
) -> Any:
    method_u = method.upper()
    timeout = aiohttp.ClientTimeout(total=retry.request_timeout_s)
    last_exc: Exception | None = None
    for attempt in range(retry.max_retries + 1):
        try:
            async with session.request(
                method_u, url, headers=headers, params=params, json=json_body, timeout=timeout
            ) as resp:
                if resp.status in (401, 403):
                    body = await resp.text()
                    raise PermissionError(f"Auth error {resp.status}: {body}")
                if 400 <= resp.status <= 499:
                    body = await resp.text()
                    raise ValueError(f"Client error {resp.status}: {body}")
                if _is_retryable_status(resp.status):
                    body = await resp.text()
                    raise RuntimeError(f"Server error {resp.status}: {body}")
                try:
                    return await resp.json()
                except Exception:
                    return await resp.text()
        except (asyncio.TimeoutError, aiohttp.ClientError, RuntimeError) as e:
            last_exc = e
            if attempt >= retry.max_retries:
                raise
            continue
    raise last_exc or RuntimeError("request_json failed unexpectedly")
