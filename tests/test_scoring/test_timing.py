"""Tests for the timing scorer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from whale_detector.db import Database
from whale_detector.models import MarketDetail, Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.timing import TimingScorer

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    gamma = AsyncMock()
    yield ScoringContext(db=db, gamma_api=gamma)
    await db.close()


def _market_ending_in(hours: float) -> MarketDetail:
    end = datetime.now(UTC) + timedelta(hours=hours)
    return MarketDetail(
        condition_id="0xcond",
        slug="test-market",
        end_date=end,
    )


class TestTimingScorer:
    async def test_no_gamma_api(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "test.db")
        await db.initialize()
        ctx = ScoringContext(db=db, gamma_api=None)
        scorer = TimingScorer()
        trade = Trade.from_api(make_trade_data())
        result = await scorer.score(trade, ctx)
        assert result.score == 0.0
        await db.close()

    async def test_no_end_date(self, context: ScoringContext) -> None:
        context.gamma_api.get_market_by_condition.return_value = (
            MarketDetail(condition_id="0xcond", slug="test")
        )
        scorer = TimingScorer()
        trade = Trade.from_api(make_trade_data())
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_trade_far_from_resolution(
        self, context: ScoringContext,
    ) -> None:
        context.gamma_api.get_market_by_condition.return_value = (
            _market_ending_in(48.0)
        )
        scorer = TimingScorer(window_hours=24.0)
        trade = Trade.from_api(make_trade_data(
            timestamp=int(datetime.now(UTC).timestamp()),
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_trade_close_to_resolution(
        self, context: ScoringContext,
    ) -> None:
        # Market ending in 6 hours, window is 24h
        end = datetime.now(UTC) + timedelta(hours=6)
        context.gamma_api.get_market_by_condition.return_value = (
            MarketDetail(
                condition_id="0xcond", slug="test",
                end_date=end,
            )
        )
        scorer = TimingScorer(window_hours=24.0)
        trade = Trade.from_api(make_trade_data(
            timestamp=int(datetime.now(UTC).timestamp()),
            price=0.50,
        ))
        result = await scorer.score(trade, context)
        # 6h out of 24h window: proximity = 1 - 6/24 = 0.75
        assert result.score == pytest.approx(0.75, abs=0.05)
        assert "6." in result.reason or "resolution" in result.reason

    async def test_minority_outcome_boost(
        self, context: ScoringContext,
    ) -> None:
        end = datetime.now(UTC) + timedelta(hours=12)
        context.gamma_api.get_market_by_condition.return_value = (
            MarketDetail(
                condition_id="0xcond", slug="test",
                end_date=end,
            )
        )
        scorer = TimingScorer(
            window_hours=24.0, minority_price_threshold=0.35,
        )
        # Low price = minority outcome
        trade = Trade.from_api(make_trade_data(
            timestamp=int(datetime.now(UTC).timestamp()),
            price=0.10,
        ))
        result = await scorer.score(trade, context)
        # proximity=0.5, minority_mult=1.5, score=0.75
        assert result.score > 0.5
        assert "minority" in result.reason

    async def test_name(self) -> None:
        assert TimingScorer().name == "timing"
