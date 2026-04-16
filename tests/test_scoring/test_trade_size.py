"""Tests for the trade size scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.trade_size import TradeSizeScorer

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


class TestTradeSizeScorer:
    async def test_below_threshold(self, context: ScoringContext) -> None:
        scorer = TradeSizeScorer(absolute_threshold=10_000)
        trade = Trade.from_api(make_trade_data(size=100.0, price=0.50))
        result = await scorer.score(trade, context)
        assert result.score == 0.0
        assert result.reason == ""

    async def test_above_absolute_threshold(self, context: ScoringContext) -> None:
        scorer = TradeSizeScorer(absolute_threshold=10_000)
        trade = Trade.from_api(make_trade_data(size=20_000.0, price=0.90))
        result = await scorer.score(trade, context)
        assert result.score == 1.0
        assert "$10,000" in result.reason

    async def test_z_score_detection(self, context: ScoringContext) -> None:
        scorer = TradeSizeScorer(absolute_threshold=100_000, z_score_threshold=2.0)

        # Insert baseline trades with some variance
        for i in range(10):
            small = Trade.from_api(
                make_trade_data(
                    size=10.0 + i, price=0.50, transactionHash=f"0xbase{i}"
                )
            )
            await context.db.insert_trade(small)

        # Now score a trade that's much larger than the baseline
        outlier = Trade.from_api(
            make_trade_data(size=500.0, price=0.50, transactionHash="0xoutlier")
        )
        result = await scorer.score(outlier, context)
        assert result.score > 0.5
        assert "stddevs" in result.reason

    async def test_no_stats_available(self, context: ScoringContext) -> None:
        """First trade in a market — no rolling stats, only absolute check."""
        scorer = TradeSizeScorer(absolute_threshold=10_000)
        trade = Trade.from_api(make_trade_data(size=50.0, price=0.50))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_zero_stddev(self, context: ScoringContext) -> None:
        """All trades same size — stddev is 0, should not crash."""
        scorer = TradeSizeScorer(absolute_threshold=100_000, z_score_threshold=3.0)

        for i in range(5):
            trade = Trade.from_api(
                make_trade_data(size=100.0, price=1.0, transactionHash=f"0xsame{i}")
            )
            await context.db.insert_trade(trade)

        test_trade = Trade.from_api(
            make_trade_data(size=100.0, price=1.0, transactionHash="0xtest")
        )
        result = await scorer.score(test_trade, context)
        # stddev is 0, so z-score should not produce a score
        assert result.score == 0.0

    async def test_scorer_name(self) -> None:
        scorer = TradeSizeScorer()
        assert scorer.name == "trade_size"
