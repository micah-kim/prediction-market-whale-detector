"""Tests for the account age scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.scoring.account_age import AccountAgeScorer
from whale_detector.scoring.base import ScoringContext

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


class TestAccountAgeScorer:
    async def test_brand_new_wallet(
        self, context: ScoringContext,
    ) -> None:
        """First trade ever from this wallet — maximum suspicion."""
        scorer = AccountAgeScorer()
        trade = Trade.from_api(make_trade_data(
            proxyWallet="0xbrand_new",
            transactionHash="0xfirst_ever",
        ))
        result = await scorer.score(trade, context)
        # Brand new, 0 trades, 0 markets → all sub-scores high
        assert result.score > 0.8
        assert "Brand new" in result.reason

    async def test_established_wallet(
        self, context: ScoringContext,
    ) -> None:
        """Wallet with many trades across multiple markets."""
        wallet = "0xestablished"
        # Insert 20 trades across 5 markets, spanning 30 days
        base_ts = 1700000000
        for i in range(20):
            trade = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                conditionId=f"0xmarket{i % 5}",
                timestamp=base_ts + i * 86400,  # 1 trade/day
                transactionHash=f"0xest{i}",
            ))
            await context.db.insert_trade(trade)

        scorer = AccountAgeScorer(
            new_wallet_days=7.0,
            min_trades_for_established=10,
            min_markets_for_diverse=3,
        )
        # New trade from same wallet
        new_trade = Trade.from_api(make_trade_data(
            proxyWallet=wallet,
            timestamp=base_ts + 30 * 86400,
            transactionHash="0xnew_from_est",
        ))
        result = await scorer.score(new_trade, context)
        # Old wallet, many trades, multiple markets
        assert result.score < 0.3

    async def test_single_market_wallet(
        self, context: ScoringContext,
    ) -> None:
        """Wallet that only trades in one market — suspicious."""
        wallet = "0xsingle_market"
        base_ts = 1700000000
        for i in range(5):
            trade = Trade.from_api(make_trade_data(
                proxyWallet=wallet,
                conditionId="0xsame_market",
                timestamp=base_ts + i * 100,
                transactionHash=f"0xsm{i}",
            ))
            await context.db.insert_trade(trade)

        scorer = AccountAgeScorer(min_markets_for_diverse=3)
        new_trade = Trade.from_api(make_trade_data(
            proxyWallet=wallet,
            conditionId="0xsame_market",
            timestamp=base_ts + 600,
            transactionHash="0xsm_new",
        ))
        result = await scorer.score(new_trade, context)
        # Low diversity should push score up
        assert "1 market" in result.reason

    async def test_name(self) -> None:
        assert AccountAgeScorer().name == "account_age"
