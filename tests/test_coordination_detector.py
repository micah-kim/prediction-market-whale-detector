"""Tests for the coordinated entry detector."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from whale_detector.coordination import CoordinatedEntryDetector
from whale_detector.db import Database
from whale_detector.models import Trade

from conftest import make_trade_data


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield db
    await db.close()


def _now() -> int:
    return int(time.time())


class TestCoordinatedEntryDetector:
    async def test_no_trades(self, db: Database) -> None:
        """Empty database → no patterns detected."""
        detector = CoordinatedEntryDetector(min_wallets=3)
        results = await detector.scan(db)
        assert results == []

    async def test_insufficient_wallets(self, db: Database) -> None:
        """Two wallets is below min_wallets=3 threshold."""
        now = _now()
        for i, wallet in enumerate(["0xwallet_a", "0xwallet_b"]):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                side="BUY",
                price=0.05,
                conditionId="0xmarket_coord",
                timestamp=now - 100 + i * 10,
                transactionHash=f"0xcoord_few_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600, min_wallets=3,
        )
        results = await detector.scan(db)
        assert results == []

    async def test_detects_coordinated_entry(self, db: Database) -> None:
        """Five fresh wallets buying minority outcome → detected."""
        now = _now()
        wallets = [f"0xcoord_wallet_{i}" for i in range(5)]

        for i, wallet in enumerate(wallets):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                side="BUY",
                price=0.05,
                size=200.0,
                conditionId="0xcoord_market",
                title="Will rare event happen?",
                outcome="Yes",
                timestamp=now - 300 + i * 30,  # spread over 2 min
                transactionHash=f"0xcoord_detect_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600,
            min_wallets=3,
            max_price=0.20,
            fresh_threshold=5,
            tight_window_seconds=1800,
            min_confidence=0.3,
        )
        results = await detector.scan(db)

        assert len(results) == 1
        entry = results[0]
        assert entry.condition_id == "0xcoord_market"
        assert len(entry.wallets) == 5
        assert entry.fresh_wallet_count == 5  # all brand new
        assert entry.total_usdc == pytest.approx(50.0)  # 5 * 200 * 0.05
        assert entry.confidence > 0.4
        assert entry.trade_count == 5

    async def test_ignores_established_wallets(self, db: Database) -> None:
        """Wallets with many prior trades reduce freshness score."""
        now = _now()
        wallets = [f"0xold_wallet_{i}" for i in range(4)]

        # Give each wallet lots of history
        for wallet in wallets:
            for j in range(20):
                t = Trade.from_api(make_trade_data(
                    proxyWallet=wallet,
                    side="BUY",
                    price=0.50,
                    conditionId=f"0xother_market_{j % 5}",
                    timestamp=now - 86400 + j * 100,
                    transactionHash=f"0xold_{wallet}_{j}",
                ))
                await db.insert_trade(t)

        # Now the coordinated entry in a new market
        for i, wallet in enumerate(wallets):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                side="BUY",
                price=0.08,
                conditionId="0xnew_coord_market",
                timestamp=now - 60 + i * 10,
                transactionHash=f"0xold_coord_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600,
            min_wallets=3,
            fresh_threshold=5,
            min_confidence=0.5,
        )
        results = await detector.scan(db)
        # With 0 fresh wallets, freshness_score=0 → lower confidence
        # Should either not detect or have low confidence
        if results:
            assert results[0].fresh_wallet_count == 0

    async def test_ignores_high_price_trades(self, db: Database) -> None:
        """Trades above max_price are not considered minority-side."""
        now = _now()
        for i in range(5):
            t = Trade.from_api(make_trade_data(
                proxyWallet=f"0xhigh_price_{i}",
                side="BUY",
                price=0.65,
                conditionId="0xhigh_price_market",
                timestamp=now - 100 + i * 10,
                transactionHash=f"0xhp_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600, min_wallets=3, max_price=0.20,
        )
        results = await detector.scan(db)
        assert results == []

    async def test_ignores_sell_side(self, db: Database) -> None:
        """SELL trades are not coordination signals."""
        now = _now()
        for i in range(5):
            t = Trade.from_api(make_trade_data(
                proxyWallet=f"0xseller_{i}",
                side="SELL",
                price=0.05,
                conditionId="0xsell_market",
                timestamp=now - 100 + i * 10,
                transactionHash=f"0xsell_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600, min_wallets=3,
        )
        results = await detector.scan(db)
        assert results == []

    async def test_time_spread_affects_confidence(self, db: Database) -> None:
        """Tighter time window → higher confidence."""
        now = _now()
        wallets = [f"0xtight_{i}" for i in range(5)]

        # All trades within 60 seconds
        for i, wallet in enumerate(wallets):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                side="BUY",
                price=0.03,
                conditionId="0xtight_market",
                timestamp=now - 60 + i * 10,
                transactionHash=f"0xtight_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600,
            min_wallets=3,
            tight_window_seconds=1800,
            min_confidence=0.0,
        )
        results = await detector.scan(db)

        assert len(results) == 1
        entry = results[0]
        # 40s spread out of 1800s window → very tight
        assert entry.time_spread_seconds <= 60
        assert entry.confidence > 0.6

    async def test_old_trades_outside_lookback(self, db: Database) -> None:
        """Trades older than lookback window are ignored."""
        now = _now()
        for i in range(5):
            t = Trade.from_api(make_trade_data(
                proxyWallet=f"0xold_trade_{i}",
                side="BUY",
                price=0.05,
                conditionId="0xold_market",
                timestamp=now - 7200,  # 2 hours ago
                transactionHash=f"0xold_t_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600,  # 1 hour
            min_wallets=3,
        )
        results = await detector.scan(db)
        assert results == []

    async def test_sorted_by_confidence(self, db: Database) -> None:
        """Multiple patterns are sorted by confidence descending."""
        now = _now()

        # Pattern 1: 3 wallets, wide spread
        for i in range(3):
            t = Trade.from_api(make_trade_data(
                proxyWallet=f"0xpattern1_{i}",
                side="BUY",
                price=0.10,
                conditionId="0xmarket_p1",
                timestamp=now - 1500 + i * 500,
                transactionHash=f"0xp1_{i}",
            ))
            await db.insert_trade(t)

        # Pattern 2: 6 wallets, tight spread, lower price
        for i in range(6):
            t = Trade.from_api(make_trade_data(
                proxyWallet=f"0xpattern2_{i}",
                side="BUY",
                price=0.03,
                conditionId="0xmarket_p2",
                timestamp=now - 60 + i * 5,
                transactionHash=f"0xp2_{i}",
            ))
            await db.insert_trade(t)

        detector = CoordinatedEntryDetector(
            lookback_seconds=3600,
            min_wallets=3,
            min_confidence=0.0,
        )
        results = await detector.scan(db)

        assert len(results) == 2
        # Pattern 2 should have higher confidence
        assert results[0].condition_id == "0xmarket_p2"
        assert results[0].confidence >= results[1].confidence
