"""Tests for the win rate scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.win_rate import WinRateScorer

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


class TestWinRateScorer:
    async def test_insufficient_trades(
        self, context: ScoringContext,
    ) -> None:
        """Less than min_resolved_trades → score 0."""
        scorer = WinRateScorer(min_resolved_trades=5)
        wallet = "0xfew_trades"
        for i in range(3):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet, price=0.10,
                transactionHash=f"0xwr{i}",
            ))
            await context.db.insert_trade(t)

        trade = Trade.from_api(make_trade_data(
            proxyWallet=wallet, price=0.10,
            transactionHash="0xwr_test",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_normal_price_wallet(
        self, context: ScoringContext,
    ) -> None:
        """Wallet with average prices > 0.20 → score 0."""
        scorer = WinRateScorer(min_resolved_trades=5)
        wallet = "0xnormal"
        for i in range(10):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet, price=0.55,
                transactionHash=f"0xnorm{i}",
            ))
            await context.db.insert_trade(t)

        trade = Trade.from_api(make_trade_data(
            proxyWallet=wallet, price=0.55,
            transactionHash="0xnorm_test",
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_longshot_pattern(
        self, context: ScoringContext,
    ) -> None:
        """Wallet consistently buying at very low prices."""
        scorer = WinRateScorer(min_resolved_trades=5)
        wallet = "0xlongshot"
        for i in range(20):
            t = Trade.from_api(make_trade_data(
                proxyWallet=wallet, price=0.05,
                transactionHash=f"0xls{i}",
            ))
            await context.db.insert_trade(t)

        trade = Trade.from_api(make_trade_data(
            proxyWallet=wallet, price=0.05,
            transactionHash="0xls_test",
        ))
        result = await scorer.score(trade, context)
        assert result.score > 0.3
        assert "long-shot" in result.reason

    async def test_name(self) -> None:
        assert WinRateScorer().name == "win_rate"
