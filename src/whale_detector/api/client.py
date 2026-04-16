"""Async HTTP client with token-bucket rate limiting and retry."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
CLOB_API_BASE = "https://clob.polymarket.com"


class RateLimiter:
    """Simple token-bucket rate limiter."""

    def __init__(self, rate: float, burst: int | None = None) -> None:
        self._rate = rate  # tokens per second
        self._burst = burst or int(rate * 2)
        self._tokens = float(self._burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1:
                wait = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait)
                self._tokens = 0
            else:
                self._tokens -= 1


class PolymarketClient:
    """Async HTTP client for Polymarket APIs with rate limiting and retry."""

    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)
        self._data_limiter = RateLimiter(rate=15.0)  # 200 req/10s, conservative
        self._gamma_limiter = RateLimiter(rate=25.0)  # 300 req/10s, conservative
        self._clob_limiter = RateLimiter(rate=15.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        base_url: str,
        path: str,
        limiter: RateLimiter,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
    ) -> Any:
        url = f"{base_url}{path}"
        for attempt in range(max_retries + 1):
            await limiter.acquire()
            try:
                response = await self._http.get(url, params=params)
                if response.status_code == 429:
                    wait = min(2**attempt + 0.5, 30)
                    logger.warning("Rate limited on %s, retrying in %.1fs", path, wait)
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError:
                if attempt == max_retries:
                    raise
                wait = 2**attempt
                logger.warning("HTTP error on %s, retrying in %ds", path, wait)
                await asyncio.sleep(wait)
            except httpx.RequestError as exc:
                if attempt == max_retries:
                    raise
                wait = 2**attempt
                logger.warning(
                    "Request error on %s: %s, retrying in %ds",
                    path, exc, wait,
                )
                await asyncio.sleep(wait)
        raise RuntimeError(f"Max retries exceeded for {url}")

    async def data_api(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        return await self._request(DATA_API_BASE, path, self._data_limiter, params)

    async def gamma_api(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        return await self._request(GAMMA_API_BASE, path, self._gamma_limiter, params)

    async def clob_api(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        return await self._request(CLOB_API_BASE, path, self._clob_limiter, params)

    async def __aenter__(self) -> PolymarketClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
