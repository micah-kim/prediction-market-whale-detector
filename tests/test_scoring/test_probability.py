"""Tests for the probability scorer."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.probability import ProbabilityScorer

from conftest import make_trade_data


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


class TestProbabilityScorer:
    async def test_normal_price_buy(
        self, context: ScoringContext,
    ) -> None:
        """BUY at a normal price (>0.15) → score 0."""
        scorer = ProbabilityScorer()
        trade = Trade.from_api(make_trade_data(
            side="BUY", price=0.50, size=1000.0,
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_sell_at_low_price(
        self, context: ScoringContext,
    ) -> None:
        """SELL at a low price is just exiting — not suspicious."""
        scorer = ProbabilityScorer()
        trade = Trade.from_api(make_trade_data(
            side="SELL", price=0.05, size=1000.0,
        ))
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_small_buy_low_prob(
        self, context: ScoringContext,
    ) -> None:
        """Small BUY at low probability — moderate score."""
        scorer = ProbabilityScorer(
            low_prob_threshold=0.15,
            size_amplifier_usd=1000.0,
        )
        # $5 at 5% probability
        trade = Trade.from_api(make_trade_data(
            side="BUY", price=0.05, size=100.0,
        ))
        result = await scorer.score(trade, context)
        # price_score = (0.15-0.05)/0.15 = 0.667
        # usdc = 5.0, size_factor = 5/1000 = 0.005
        # raw = 0.667 * (0.5 + 0.5*0.005) ≈ 0.335
        assert 0.2 < result.score < 0.5
        assert "5.0%" in result.reason

    async def test_large_buy_low_prob(
        self, context: ScoringContext,
    ) -> None:
        """Large BUY at very low probability — high score."""
        scorer = ProbabilityScorer(
            low_prob_threshold=0.15,
            size_amplifier_usd=1000.0,
        )
        # $500 at 3% probability
        trade = Trade.from_api(make_trade_data(
            side="BUY", price=0.03, size=16667.0,
        ))
        result = await scorer.score(trade, context)
        # price_score = (0.15-0.03)/0.15 = 0.80
        # usdc = 500, size_factor = min(500/1000, 1) = 0.5
        # raw = 0.80 * (0.5 + 0.5*0.5) = 0.80 * 0.75 = 0.60
        assert result.score > 0.5
        assert "3.0%" in result.reason

    async def test_huge_buy_at_1_percent(
        self, context: ScoringContext,
    ) -> None:
        """$72K at 1% — the Iran ceasefire case study pattern."""
        scorer = ProbabilityScorer(
            low_prob_threshold=0.15,
            size_amplifier_usd=1000.0,
        )
        # 72000 shares at $0.01 each = $720 usdc
        trade = Trade.from_api(make_trade_data(
            side="BUY", price=0.01, size=72000.0,
        ))
        result = await scorer.score(trade, context)
        # price_score = (0.15-0.01)/0.15 ≈ 0.933
        # usdc = 720, size_factor = 0.72
        # raw = 0.933 * (0.5 + 0.36) ≈ 0.80
        assert result.score > 0.7
        assert "1.0%" in result.reason

    async def test_name(self) -> None:
        assert ProbabilityScorer().name == "probability"
