"""Coordinated entry detector — finds bursts of fresh wallets on minority outcomes."""

from __future__ import annotations

import logging
import time

from whale_detector.db import Database
from whale_detector.models import CoordinatedEntry

logger = logging.getLogger(__name__)


class CoordinatedEntryDetector:
    """Scans recent trades for coordinated minority-side entry patterns.

    For each market with recent minority-side BUY activity from multiple
    distinct wallets, checks whether the entries cluster tightly in time
    and come from fresh (low-history) wallets. Produces a
    ``CoordinatedEntry`` with a confidence score when the pattern is
    strong enough.

    Confidence scoring:
        - wallet_score: more distinct wallets → higher (3=0.33, 5=0.67, 8+=1.0)
        - freshness_score: fraction of participating wallets that are "fresh"
        - tightness_score: entries within a short window score higher
        - price_score: lower average price → more extreme minority bet
        - confidence = average of all four sub-scores
    """

    def __init__(
        self,
        lookback_seconds: int = 3600,
        min_wallets: int = 3,
        max_price: float = 0.20,
        fresh_threshold: int = 5,
        tight_window_seconds: int = 1800,
        min_confidence: float = 0.4,
    ) -> None:
        self._lookback = lookback_seconds
        self._min_wallets = min_wallets
        self._max_price = max_price
        self._fresh_threshold = fresh_threshold
        self._tight_window = tight_window_seconds
        self._min_confidence = min_confidence

    async def scan(self, db: Database) -> list[CoordinatedEntry]:
        """Scan the database for coordinated entry patterns.

        Returns a list of ``CoordinatedEntry`` objects for each market
        where the pattern confidence exceeds ``min_confidence``.
        """
        now = int(time.time())
        since = now - self._lookback

        # Step 1: find markets with enough distinct minority-side buyers
        active_markets = await db.get_active_minority_markets(
            since_timestamp=since,
            max_price=self._max_price,
            min_wallets=self._min_wallets,
        )

        if not active_markets:
            return []

        results: list[CoordinatedEntry] = []

        for condition_id in active_markets:
            entry = await self._analyze_market(db, condition_id, since)
            if entry is not None:
                results.append(entry)

        results.sort(key=lambda e: e.confidence, reverse=True)
        return results

    async def _analyze_market(
        self,
        db: Database,
        condition_id: str,
        since: int,
    ) -> CoordinatedEntry | None:
        """Analyze a single market for coordinated entry patterns."""
        trades = await db.get_recent_market_entries(
            condition_id=condition_id,
            since_timestamp=since,
            side="BUY",
            max_price=self._max_price,
        )

        if not trades:
            return None

        # Collect distinct wallets
        wallets = list({t.proxy_wallet for t in trades})
        if len(wallets) < self._min_wallets:
            return None

        # Check wallet freshness in batch
        counts = await db.get_wallet_trade_counts_batch(wallets)
        fresh_count = sum(
            1 for w in wallets
            if counts.get(w, 0) <= self._fresh_threshold
        )

        # Compute timing spread
        timestamps = [t.timestamp for t in trades]
        first_ts = min(timestamps)
        last_ts = max(timestamps)
        time_spread = last_ts - first_ts

        # Compute aggregate values
        total_usdc = sum(t.usdc_value for t in trades)
        avg_price = sum(t.price for t in trades) / len(trades)

        # Use the first trade for market metadata
        sample = trades[0]

        # --- Confidence sub-scores ---

        # More wallets → higher score (3=0.33, 5=0.67, 8+=1.0)
        wallet_score = min((len(wallets) - 2) / 6.0, 1.0)

        # Higher fraction of fresh wallets → higher score
        freshness_score = fresh_count / len(wallets) if wallets else 0.0

        # Tighter time window → higher score
        if time_spread <= 0:
            tightness_score = 1.0  # all at exactly the same time
        else:
            tightness_score = max(
                0.0, 1.0 - time_spread / self._tight_window
            )

        # Lower average price → more extreme → higher score
        price_score = max(0.0, 1.0 - avg_price / self._max_price)

        confidence = (
            wallet_score + freshness_score + tightness_score + price_score
        ) / 4.0

        if confidence < self._min_confidence:
            logger.debug(
                "Market %s below confidence threshold: %.2f",
                condition_id[:12],
                confidence,
            )
            return None

        return CoordinatedEntry(
            condition_id=condition_id,
            market_title=sample.title,
            market_slug=sample.slug,
            outcome=sample.outcome,
            avg_price=avg_price,
            wallets=wallets,
            fresh_wallet_count=fresh_count,
            total_usdc=total_usdc,
            time_spread_seconds=float(time_spread),
            first_entry=first_ts,
            last_entry=last_ts,
            confidence=confidence,
            trade_count=len(trades),
        )
