"""Statistical accuracy tests for the anomaly detection system.

These tests validate that:
1. The rolling stats (mean, stddev) computed by the DB match numpy/manual calculations
2. The z-score scorer correctly identifies outliers in realistic trade distributions
3. Edge cases are handled (skewed distributions, small samples, multiple markets)
4. The scoring thresholds produce sensible results for real-world whale detection
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.scoring.base import ScoringContext
from whale_detector.scoring.trade_size import TradeSizeScorer

from conftest import make_trade_data

CONDITION_A = "0xcondition_market_A"
CONDITION_B = "0xcondition_market_B"


@pytest.fixture
async def context(tmp_path: Path) -> ScoringContext:
    db = Database(tmp_path / "test.db")
    await db.initialize()
    yield ScoringContext(db=db)
    await db.close()


async def _insert_trades(
    db: Database,
    sizes: list[float],
    price: float = 1.0,
    condition_id: str = CONDITION_A,
    start_timestamp: int = 1000,
) -> None:
    """Helper to insert trades with given sizes into the DB."""
    for i, size in enumerate(sizes):
        trade = Trade.from_api(
            make_trade_data(
                size=size,
                price=price,
                conditionId=condition_id,
                transactionHash=f"0x{condition_id}_{i}",
                timestamp=start_timestamp + i,
            )
        )
        await db.insert_trade(trade)


def _manual_mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _manual_stddev_pop(values: list[float]) -> float:
    """Population standard deviation (matches SQL AVG of squared deviations)."""
    m = _manual_mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


class TestRollingStatsAccuracy:
    """Verify that the DB rolling stats match manual calculations exactly."""

    async def test_uniform_distribution(self, context: ScoringContext) -> None:
        """Evenly spaced values — easy to verify by hand."""
        sizes = [10.0, 20.0, 30.0, 40.0, 50.0]
        await _insert_trades(context.db, sizes)

        stats = await context.db.get_rolling_stats(CONDITION_A)
        assert stats is not None
        assert stats.mean == pytest.approx(_manual_mean(sizes))
        assert stats.stddev == pytest.approx(_manual_stddev_pop(sizes))
        assert stats.count == 5

    async def test_realistic_trade_distribution(
        self, context: ScoringContext,
    ) -> None:
        """Simulate a real market: many small trades, few medium ones.

        Most Polymarket trades are $5-$50. This tests that our stats
        computation is correct on a realistic distribution.
        """
        random.seed(42)
        # Log-normal-ish: mostly small, some medium
        sizes = [round(random.lognormvariate(2.5, 0.8), 2) for _ in range(100)]
        # price=1.0 so usdc_value == size
        await _insert_trades(context.db, sizes)

        stats = await context.db.get_rolling_stats(CONDITION_A)
        assert stats is not None
        assert stats.count == 100
        assert stats.mean == pytest.approx(_manual_mean(sizes), rel=1e-6)
        assert stats.stddev == pytest.approx(
            _manual_stddev_pop(sizes), rel=1e-6,
        )

    async def test_rolling_window_limits(
        self, context: ScoringContext,
    ) -> None:
        """Only the most recent N trades should be used for stats."""
        # Insert 20 trades: first 10 are large, last 10 are small
        old = [1000.0] * 10
        new = [10.0] * 10
        await _insert_trades(context.db, old + new)

        # With window=10, should only see the recent small trades
        stats = await context.db.get_rolling_stats(CONDITION_A, window=10)
        assert stats is not None
        assert stats.count == 10
        assert stats.mean == pytest.approx(10.0)
        assert stats.stddev == pytest.approx(0.0)

        # With window=20, should see all trades
        stats_all = await context.db.get_rolling_stats(CONDITION_A, window=20)
        assert stats_all is not None
        assert stats_all.count == 20
        assert stats_all.mean == pytest.approx(505.0)

    async def test_price_affects_usdc_value(
        self, context: ScoringContext,
    ) -> None:
        """Verify that usdc_value (size * price) is what gets stored and
        used for stats, not raw share count."""
        # 100 shares at $0.10 = $10 usdc_value
        # 100 shares at $0.90 = $90 usdc_value
        t1 = Trade.from_api(
            make_trade_data(
                size=100.0, price=0.10,
                conditionId=CONDITION_A, transactionHash="0xlow_price",
            )
        )
        t2 = Trade.from_api(
            make_trade_data(
                size=100.0, price=0.90,
                conditionId=CONDITION_A, transactionHash="0xhigh_price",
            )
        )
        await context.db.insert_trade(t1)
        await context.db.insert_trade(t2)

        stats = await context.db.get_rolling_stats(CONDITION_A)
        assert stats is not None
        # Mean of $10 and $90 = $50
        assert stats.mean == pytest.approx(50.0)
        # Stddev of [10, 90] = 40.0
        assert stats.stddev == pytest.approx(40.0)


class TestZScoreDetection:
    """Verify z-score scoring produces correct results for whale detection."""

    async def test_known_z_score(self, context: ScoringContext) -> None:
        """Manually verify z-score calculation against known values."""
        # Insert 5 trades: [10, 20, 30, 40, 50]
        # Mean = 30, stddev = sqrt(200) ≈ 14.14
        sizes = [10.0, 20.0, 30.0, 40.0, 50.0]
        await _insert_trades(context.db, sizes)

        mean = 30.0
        stddev = _manual_stddev_pop(sizes)  # ≈ 14.14

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,  # disable absolute
            z_score_threshold=3.0,
        )

        # A trade at $100: z = (100 - 30) / 14.14 ≈ 4.95
        # normalized = min(4.95 / 3.0, 1.0) = 1.0
        outlier = Trade.from_api(
            make_trade_data(
                size=100.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xtest",
            )
        )
        result = await scorer.score(outlier, context)
        expected_z = (100.0 - mean) / stddev
        assert expected_z > 3.0  # should exceed threshold
        assert result.score == pytest.approx(1.0)
        assert "stddevs" in result.reason

    async def test_trade_slightly_above_average(
        self, context: ScoringContext,
    ) -> None:
        """A trade 1 stddev above should score ~0.33 with z_threshold=3."""
        sizes = [10.0, 20.0, 30.0, 40.0, 50.0]
        await _insert_trades(context.db, sizes)

        mean = 30.0
        stddev = _manual_stddev_pop(sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,
            z_score_threshold=3.0,
        )

        # Trade at exactly 1 stddev above mean
        one_sd_above = mean + stddev
        trade = Trade.from_api(
            make_trade_data(
                size=one_sd_above, price=1.0,
                conditionId=CONDITION_A, transactionHash="0x1sd",
            )
        )
        result = await scorer.score(trade, context)
        # z = 1.0, normalized = 1.0 / 3.0 ≈ 0.33
        assert result.score == pytest.approx(1.0 / 3.0, abs=0.01)

    async def test_trade_below_average_scores_zero(
        self, context: ScoringContext,
    ) -> None:
        """Trades at or below the mean should score 0."""
        sizes = [10.0, 20.0, 30.0, 40.0, 50.0]
        await _insert_trades(context.db, sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,
            z_score_threshold=3.0,
        )

        # Trade below the mean ($30)
        trade = Trade.from_api(
            make_trade_data(
                size=15.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xbelow",
            )
        )
        result = await scorer.score(trade, context)
        assert result.score == 0.0

    async def test_score_capped_at_one(self, context: ScoringContext) -> None:
        """Even extremely large outliers should not exceed score 1.0."""
        sizes = [10.0, 20.0, 30.0]
        await _insert_trades(context.db, sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,
            z_score_threshold=2.0,
        )

        # Extremely large trade — z-score will be huge
        monster = Trade.from_api(
            make_trade_data(
                size=100_000.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xmonster",
            )
        )
        result = await scorer.score(monster, context)
        assert result.score == 1.0  # capped, not > 1.0


class TestMarketIsolation:
    """Verify that stats are computed per-market, not globally."""

    async def test_different_markets_independent(
        self, context: ScoringContext,
    ) -> None:
        """A large trade in market A should not affect scoring in market B."""
        # Market A: small trades ($10 each)
        await _insert_trades(
            context.db, [10.0, 10.0, 10.0, 10.0, 10.0, 11.0],
            condition_id=CONDITION_A,
        )
        # Market B: large trades ($10,000 each)
        await _insert_trades(
            context.db, [10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 10001.0],
            condition_id=CONDITION_B,
        )

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,
            z_score_threshold=3.0,
        )

        # A $100 trade in market A is a huge outlier
        trade_a = Trade.from_api(
            make_trade_data(
                size=100.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xa_outlier",
            )
        )
        result_a = await scorer.score(trade_a, context)
        assert result_a.score > 0.9  # very anomalous for market A

        # A $100 trade in market B is below average
        trade_b = Trade.from_api(
            make_trade_data(
                size=100.0, price=1.0,
                conditionId=CONDITION_B, transactionHash="0xb_normal",
            )
        )
        result_b = await scorer.score(trade_b, context)
        assert result_b.score == 0.0  # below mean for market B


class TestRealisticWhaleScenarios:
    """Test scenarios modeled after the case studies in docs/research/."""

    async def test_election_market_whale(
        self, context: ScoringContext,
    ) -> None:
        """Case study: 2024 US election — 4 accounts bet >$30M.

        Simulate a market with normal $50-$500 trades, then a $30K+ trade.
        With default $10K threshold, this should score 1.0 via absolute
        AND via z-score.
        """
        random.seed(123)
        # 200 normal trades between $50 and $500
        normal_sizes = [round(random.uniform(50, 500), 2) for _ in range(200)]
        await _insert_trades(context.db, normal_sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=10_000,
            z_score_threshold=3.0,
        )

        # Whale drops $30,000
        whale = Trade.from_api(
            make_trade_data(
                size=30_000.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xwhale",
            )
        )
        result = await scorer.score(whale, context)
        assert result.score == 1.0
        # Should trigger BOTH reasons
        assert "$10,000" in result.reason  # absolute
        assert "stddevs" in result.reason  # z-score

    async def test_niche_market_relative_whale(
        self, context: ScoringContext,
    ) -> None:
        """A niche market where normal trades are $1-$10.

        A $200 trade is not a whale by absolute standards ($10K),
        but is a massive outlier for this market.
        """
        random.seed(456)
        # 50 tiny trades between $1 and $10
        small_sizes = [round(random.uniform(1, 10), 2) for _ in range(50)]
        await _insert_trades(context.db, small_sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=10_000,  # default
            z_score_threshold=3.0,
        )

        # $200 trade — small globally, huge for this market
        relative_whale = Trade.from_api(
            make_trade_data(
                size=200.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xrelwhale",
            )
        )
        result = await scorer.score(relative_whale, context)
        # Z-score is massive (82+ stddevs), so score hits 1.0
        # The key insight: it scores high via z-score alone,
        # even though it's below the absolute threshold
        assert result.score == 1.0
        assert "stddevs" in result.reason
        assert "$10,000" not in result.reason  # absolute did NOT fire

    async def test_high_volume_market_normal_large_trade(
        self, context: ScoringContext,
    ) -> None:
        """On a high-volume market (election-scale), a $5K trade is normal.

        Should NOT trigger z-score even though $5K sounds large.
        """
        random.seed(789)
        # Simulate a deep market: trades between $500 and $10,000
        big_market = [
            round(random.uniform(500, 10_000), 2) for _ in range(200)
        ]
        await _insert_trades(context.db, big_market)

        scorer = TradeSizeScorer(
            absolute_threshold=10_000,
            z_score_threshold=3.0,
        )

        # $5,000 trade — within normal range for this market
        trade = Trade.from_api(
            make_trade_data(
                size=5_000.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xnormal5k",
            )
        )
        result = await scorer.score(trade, context)
        # Below absolute threshold
        # Z-score should be close to 0 (trade is near the mean)
        assert result.score < 0.5

    async def test_skewed_distribution(
        self, context: ScoringContext,
    ) -> None:
        """Real trade distributions are right-skewed (many small, few large).

        Verify that the scorer still works when the distribution has a
        long tail. A trade in the tail should score high even though
        there are already some larger trades.
        """
        random.seed(101)
        # 90 trades: $5-$20 (the bulk)
        # 10 trades: $100-$500 (occasional larger trades)
        sizes = [round(random.uniform(5, 20), 2) for _ in range(90)]
        sizes += [round(random.uniform(100, 500), 2) for _ in range(10)]
        random.shuffle(sizes)
        await _insert_trades(context.db, sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=999_999,
            z_score_threshold=3.0,
        )

        mean = _manual_mean(sizes)
        stddev = _manual_stddev_pop(sizes)

        # A trade 5 stddevs above the mean
        extreme = mean + 5 * stddev
        trade = Trade.from_api(
            make_trade_data(
                size=extreme, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xskewed",
            )
        )
        result = await scorer.score(trade, context)
        assert result.score == 1.0  # 5 stddevs > 3 threshold

    async def test_fresh_market_insufficient_data(
        self, context: ScoringContext,
    ) -> None:
        """A brand new market with only 1 trade cannot compute z-scores.

        This is important: the very first trade in a market should not
        produce a z-score alert (we have no baseline to compare against).
        The absolute threshold should still work.
        """
        await _insert_trades(context.db, [50.0])

        scorer = TradeSizeScorer(
            absolute_threshold=100,
            z_score_threshold=3.0,
        )

        # Second trade of $500
        trade = Trade.from_api(
            make_trade_data(
                size=500.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xearly",
            )
        )
        result = await scorer.score(trade, context)
        # Above $100 absolute, so score = 1.0
        assert result.score == 1.0
        # But the reason should only mention absolute, not z-score
        # (only 1 prior trade — stats computed but sample is tiny)
        assert "$100" in result.reason


class TestScorerInteraction:
    """Test how absolute and z-score methods interact."""

    async def test_absolute_wins_when_z_score_unavailable(
        self, context: ScoringContext,
    ) -> None:
        """With no prior trades, only absolute threshold fires."""
        scorer = TradeSizeScorer(absolute_threshold=1_000)

        trade = Trade.from_api(
            make_trade_data(
                size=5_000.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xabs_only",
            )
        )
        result = await scorer.score(trade, context)
        assert result.score == 1.0
        assert "$1,000" in result.reason

    async def test_z_score_wins_when_below_absolute(
        self, context: ScoringContext,
    ) -> None:
        """Z-score can trigger even when absolute threshold is not met."""
        # Tiny market: trades of $1-$2
        sizes = [1.0, 1.5, 2.0, 1.0, 1.5, 2.0, 1.0, 1.5, 2.0, 1.0]
        await _insert_trades(context.db, sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=10_000,  # won't trigger
            z_score_threshold=3.0,
        )

        # $20 trade — tiny globally, massive for this market
        trade = Trade.from_api(
            make_trade_data(
                size=20.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xz_only",
            )
        )
        result = await scorer.score(trade, context)
        assert result.score > 0.9
        assert "stddevs" in result.reason
        assert "$10,000" not in result.reason

    async def test_both_fire_together(
        self, context: ScoringContext,
    ) -> None:
        """When both methods trigger, both reasons appear and score = 1.0."""
        sizes = [10.0, 20.0, 30.0, 15.0, 25.0]
        await _insert_trades(context.db, sizes)

        scorer = TradeSizeScorer(
            absolute_threshold=500,
            z_score_threshold=3.0,
        )

        trade = Trade.from_api(
            make_trade_data(
                size=1_000.0, price=1.0,
                conditionId=CONDITION_A, transactionHash="0xboth",
            )
        )
        result = await scorer.score(trade, context)
        assert result.score == 1.0
        assert "$500" in result.reason
        assert "stddevs" in result.reason
