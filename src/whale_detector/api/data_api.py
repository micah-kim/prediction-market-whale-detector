"""Polymarket Data API client — trade and activity endpoints."""

from __future__ import annotations

import logging
from typing import Any

from whale_detector.api.client import PolymarketClient
from whale_detector.config import MarketFilter
from whale_detector.models import Trade

logger = logging.getLogger(__name__)


class DataAPI:
    """Wrapper around the Polymarket Data API for trade monitoring."""

    def __init__(
        self, client: PolymarketClient, market_filter: MarketFilter,
    ) -> None:
        self._client = client
        self._filter = market_filter

    async def get_recent_trades(
        self,
        limit: int = 100,
        after_timestamp: int | None = None,
        max_pages: int = 5,
    ) -> list[Trade]:
        """Fetch recent trades, paginating to avoid gaps during busy periods.

        If a page returns a full ``limit`` of results, the next page is
        fetched automatically (up to ``max_pages`` total) so that we
        don't miss trades between poll cycles.
        """
        all_trades: list[Trade] = []
        cursor_ts = after_timestamp

        for _ in range(max_pages):
            params: dict[str, Any] = {"limit": limit}
            if cursor_ts is not None:
                params["after"] = cursor_ts

            raw = await self._client.data_api("/trades", params=params)

            if not isinstance(raw, list):
                logger.warning(
                    "Unexpected response type from /trades: %s",
                    type(raw),
                )
                break

            page_trades: list[Trade] = []
            for item in raw:
                try:
                    trade = Trade.from_api(item)
                except (KeyError, ValueError) as exc:
                    logger.debug("Skipping malformed trade: %s", exc)
                    continue

                if not self._filter.is_watched(trade.slug):
                    continue

                page_trades.append(trade)

            all_trades.extend(page_trades)

            # Stop if we got fewer than the limit — we've caught up
            if len(raw) < limit:
                break

            # Advance cursor to the latest timestamp in this page
            if raw:
                cursor_ts = max(int(item.get("timestamp", 0)) for item in raw)

        return all_trades

    async def get_user_activity(
        self, address: str, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch trading activity for a wallet address."""
        raw = await self._client.data_api(
            "/activity", params={"user": address, "limit": limit},
        )
        if isinstance(raw, list):
            return raw
        return []

    async def get_user_positions(
        self, address: str,
    ) -> list[dict[str, Any]]:
        """Fetch current positions for a wallet address."""
        raw = await self._client.data_api(
            "/positions", params={"user": address},
        )
        if isinstance(raw, list):
            return raw
        return []
