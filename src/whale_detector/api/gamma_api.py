"""Polymarket Gamma API client — market metadata endpoints."""

from __future__ import annotations

import logging
import time

from whale_detector.api.client import PolymarketClient
from whale_detector.models import MarketDetail

logger = logging.getLogger(__name__)


class GammaAPI:
    """Wrapper around the Polymarket Gamma API for market metadata.

    Includes an in-memory TTL cache to avoid redundant API calls
    for the same market.
    """

    def __init__(
        self, client: PolymarketClient, cache_ttl: int = 300,
    ) -> None:
        self._client = client
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[MarketDetail, float]] = {}

    async def get_market_detail(
        self, slug: str,
    ) -> MarketDetail | None:
        """Fetch market metadata by slug, with caching."""
        now = time.monotonic()

        if slug in self._cache:
            detail, cached_at = self._cache[slug]
            if now - cached_at < self._cache_ttl:
                return detail

        try:
            raw = await self._client.gamma_api(
                "/markets", params={"slug": slug},
            )
        except Exception:
            logger.debug("Failed to fetch market detail for %s", slug)
            return None

        if not raw:
            return None

        # The API returns a list for slug queries
        items = raw if isinstance(raw, list) else [raw]
        if not items:
            return None

        data = items[0]
        try:
            detail = MarketDetail.from_api(data)
        except (KeyError, ValueError) as exc:
            logger.debug("Failed to parse market %s: %s", slug, exc)
            return None

        self._cache[slug] = (detail, now)
        return detail

    async def get_market_by_condition(
        self, condition_id: str,
    ) -> MarketDetail | None:
        """Fetch market metadata by condition ID."""
        now = time.monotonic()
        cache_key = f"cond:{condition_id}"

        if cache_key in self._cache:
            detail, cached_at = self._cache[cache_key]
            if now - cached_at < self._cache_ttl:
                return detail

        try:
            raw = await self._client.gamma_api(
                "/markets",
                params={"condition_id": condition_id},
            )
        except Exception:
            logger.debug(
                "Failed to fetch market for condition %s",
                condition_id,
            )
            return None

        if not raw:
            return None

        items = raw if isinstance(raw, list) else [raw]
        if not items:
            return None

        try:
            detail = MarketDetail.from_api(items[0])
        except (KeyError, ValueError):
            return None

        self._cache[cache_key] = (detail, now)
        return detail

    async def get_market_from_clob(
        self, condition_id: str,
    ) -> MarketDetail | None:
        """Fetch market data from the CLOB API (fallback for micro-markets).

        Some short-lived markets (crypto up/down, sports) aren't indexed
        by the Gamma API but exist on the CLOB API.
        """
        now = time.monotonic()
        cache_key = f"clob:{condition_id}"

        if cache_key in self._cache:
            detail, cached_at = self._cache[cache_key]
            if now - cached_at < self._cache_ttl:
                return detail

        try:
            raw = await self._client.clob_api(f"/markets/{condition_id}")
        except Exception:
            logger.debug(
                "Failed to fetch CLOB market for condition %s",
                condition_id[:16],
            )
            return None

        if not raw:
            return None

        tokens = raw.get("tokens", [])
        outcomes = [t.get("outcome", "") for t in tokens]
        outcome_prices = [float(t.get("price", 0)) for t in tokens]

        detail = MarketDetail(
            condition_id=raw.get("condition_id", condition_id),
            slug="",
            question=raw.get("question", ""),
            active=bool(raw.get("active", True)),
            closed=bool(raw.get("closed", False)),
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )

        self._cache[cache_key] = (detail, now)
        return detail
