"""Tests for the coordination scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import CoordinatedEntry, Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.coordination import CoordinationScorer

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


def _make_entry(**overrides) -> CoordinatedEntry:
    base = dict(
        condition_id="0xcoord_market",
        market_title="Will rare event happen?",
        market_slug="rare-event",
        outcome="Yes",
        avg_price=0.05,
        wallets=["0xwallet_a", "0xwallet_b", "0xwallet_c"],
        fresh_wallet_count=3,
        total_usdc=150.0,
        time_spread_seconds=120.0,
        first_entry=1700000000,
        last_entry=1700000120,
        confidence=0.75,
        trade_count=3,
    )
    base.update(overrides)
    return CoordinatedEntry(**base)


class TestCoordinationScorer:
    async def test_no_entries(self, context: ScoringContext) -> None:
        """No coordinated entries → score 0."""
        scorer = CoordinationScorer()
        trade = Trade.from_api(make_trade_data(
            proxyWallet="0xwallet_a",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_wallet_not_in_entry(self, context: ScoringContext) -> None:
        """Trade wallet not part of any coordinated entry → score 0."""
        context.coordinated_entries = [_make_entry()]
        scorer = CoordinationScorer()
        trade = Trade.from_api(make_trade_data(
            proxyWallet="0xunrelated_wallet",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_wallet_in_entry(self, context: ScoringContext) -> None:
        """Trade wallet is part of a coordinated entry → score = confidence."""
        entry = _make_entry(confidence=0.75)
        context.coordinated_entries = [entry]
        scorer = CoordinationScorer()
        trade = Trade.from_api(make_trade_data(
            proxyWallet="0xwallet_b",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.75
        assert "coordinated entry" in result.reason
        assert "3 wallets" in result.reason

    async def test_multiple_entries_first_match(
        self, context: ScoringContext,
    ) -> None:
        """Wallet in first matching entry uses that entry's confidence."""
        entry1 = _make_entry(
            condition_id="0xmarket_1",
            wallets=["0xwallet_x", "0xwallet_y", "0xwallet_z"],
            confidence=0.6,
        )
        entry2 = _make_entry(
            condition_id="0xmarket_2",
            wallets=["0xwallet_a", "0xwallet_b", "0xwallet_c"],
            confidence=0.9,
        )
        context.coordinated_entries = [entry1, entry2]
        scorer = CoordinationScorer()
        trade = Trade.from_api(make_trade_data(
            proxyWallet="0xwallet_a",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.9

    async def test_name(self) -> None:
        assert CoordinationScorer().name == "coordination"
