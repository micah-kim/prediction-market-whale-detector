"""Tests for paper trading — PaperTrader and DB methods."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from conftest import make_trade_data

from whale_detector.db import Database
from whale_detector.models import Alert, MarketDetail, ScoreResult, Trade
from whale_detector.paper_trading import PaperTrader


@pytest.fixture
async def paper_db(tmp_path: Path) -> Database:
    """Database initialized with paper trading tables."""
    db = Database(tmp_path / "paper.db")
    await db.initialize()
    await db.initialize_paper_trading(10_000.0)
    yield db
    await db.close()


def _make_alert(
    score: float = 0.85,
    price: float = 0.10,
    size: float = 5000.0,
    side: str = "BUY",
    condition_id: str = "0xcond1",
    outcome: str = "Yes",
    tx_hash: str = "0xpaper_1",
) -> Alert:
    trade = Trade.from_api(make_trade_data(
        size=size,
        price=price,
        side=side,
        conditionId=condition_id,
        outcome=outcome,
        transactionHash=tx_hash,
    ))
    return Alert(
        trade=trade,
        scores=[ScoreResult(
            scorer_name="trade_size",
            score=score,
            reason="Test",
        )],
        composite_score=score,
    )


class TestPaperTraderOnAlert:
    async def test_creates_paper_trade(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()
        alert = _make_alert()

        result = await trader.on_alert(alert)

        assert result is True
        trades = await paper_db.get_paper_trades()
        assert len(trades) == 1
        assert trades[0]["status"] == "open"
        assert trades[0]["outcome"] == "Yes"

    async def test_skips_low_score(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db, min_alert_score=0.6)
        await trader.initialize()
        alert = _make_alert(score=0.3)

        result = await trader.on_alert(alert)

        assert result is False
        assert len(await paper_db.get_paper_trades()) == 0

    async def test_skips_sell_side(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()
        alert = _make_alert(side="SELL")

        result = await trader.on_alert(alert)

        assert result is False

    async def test_deducts_from_bankroll(self, paper_db: Database) -> None:
        trader = PaperTrader(
            paper_db, initial_bankroll=10_000, risk_per_trade_pct=0.02,
        )
        await trader.initialize()
        alert = _make_alert(price=0.10)

        await trader.on_alert(alert)

        bankroll = await paper_db.get_paper_bankroll()
        # Cost = 0.02 * 10000 = $200 worth of shares
        assert bankroll is not None
        assert bankroll["current_bankroll"] < 10_000


class TestPaperTraderSettle:
    async def test_settle_winning(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()
        alert = _make_alert(
            price=0.10, condition_id="0xwin", outcome="Yes",
        )
        await trader.on_alert(alert)

        settled = await trader.settle_market("0xwin", "Yes")

        assert settled == 1
        trades = await paper_db.get_paper_trades(status="won")
        assert len(trades) == 1
        assert trades[0]["exit_price"] == 1.0
        assert trades[0]["pnl"] is not None
        assert trades[0]["pnl"] > 0

    async def test_settle_losing(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()
        alert = _make_alert(
            price=0.10, condition_id="0xlose", outcome="Yes",
        )
        await trader.on_alert(alert)

        settled = await trader.settle_market("0xlose", "No")

        assert settled == 1
        trades = await paper_db.get_paper_trades(status="lost")
        assert len(trades) == 1
        assert trades[0]["exit_price"] == 0.0
        assert trades[0]["pnl"] < 0

    async def test_settle_no_open_trades(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()

        settled = await trader.settle_market("0xnone", "Yes")
        assert settled == 0


class TestPaperSummary:
    async def test_empty_summary(self, paper_db: Database) -> None:
        summary = await paper_db.get_paper_summary()
        assert summary["total_trades"] == 0
        assert summary["win_rate"] == 0.0
        assert summary["initial_bankroll"] == 10_000.0

    async def test_summary_after_trades(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()

        await trader.on_alert(_make_alert(
            condition_id="0xm1", outcome="Yes", tx_hash="0xt1",
        ))
        await trader.on_alert(_make_alert(
            condition_id="0xm2", outcome="No", tx_hash="0xt2",
        ))
        await trader.settle_market("0xm1", "Yes")  # win
        await trader.settle_market("0xm2", "Yes")  # lose (bet No)

        summary = await paper_db.get_paper_summary()
        assert summary["total_trades"] == 2
        assert summary["won"] == 1
        assert summary["lost"] == 1
        assert summary["win_rate"] == 0.5


class TestPaperReset:
    async def test_resets_data(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db)
        await trader.initialize()
        await trader.on_alert(_make_alert())

        assert len(await paper_db.get_paper_trades()) == 1

        await paper_db.reset_paper_trading(10_000.0)

        assert len(await paper_db.get_paper_trades()) == 0
        bankroll = await paper_db.get_paper_bankroll()
        assert bankroll["current_bankroll"] == 10_000.0
        assert bankroll["total_deployed"] == 0.0
        assert bankroll["total_realized_pnl"] == 0.0


class TestCheckResolutions:
    async def test_settles_closed_market(self, paper_db: Database) -> None:
        gamma = AsyncMock()
        gamma.get_market_detail.return_value = MarketDetail(
            condition_id="0xcond1",
            slug="will-x-happen",
            closed=True,
            active=False,
            outcomes=["Yes", "No"],
            outcome_prices=[1.0, 0.0],
        )
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()
        await trader.on_alert(_make_alert(outcome="Yes"))

        settled = await trader.check_resolutions()

        assert settled == 1
        trades = await paper_db.get_paper_trades(status="won")
        assert len(trades) == 1

    async def test_skips_open_market(self, paper_db: Database) -> None:
        gamma = AsyncMock()
        gamma.get_market_detail.return_value = MarketDetail(
            condition_id="0xcond1",
            slug="will-x-happen",
            closed=False,
            active=True,
            outcomes=["Yes", "No"],
            outcome_prices=[0.6, 0.4],
        )
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()
        await trader.on_alert(_make_alert(outcome="Yes"))

        settled = await trader.check_resolutions()

        assert settled == 0
        trades = await paper_db.get_paper_trades(status="open")
        assert len(trades) == 1

    async def test_no_gamma_api(self, paper_db: Database) -> None:
        trader = PaperTrader(paper_db, gamma_api=None)
        await trader.initialize()
        await trader.on_alert(_make_alert())

        settled = await trader.check_resolutions()
        assert settled == 0

    async def test_no_open_trades(self, paper_db: Database) -> None:
        gamma = AsyncMock()
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()

        settled = await trader.check_resolutions()
        assert settled == 0
        gamma.get_market_detail.assert_not_called()

    async def test_losing_resolution(self, paper_db: Database) -> None:
        gamma = AsyncMock()
        gamma.get_market_detail.return_value = MarketDetail(
            condition_id="0xcond1",
            slug="will-x-happen",
            closed=True,
            active=False,
            outcomes=["Yes", "No"],
            outcome_prices=[0.0, 1.0],  # "No" wins
        )
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()
        await trader.on_alert(_make_alert(outcome="Yes"))  # We bet "Yes"

        settled = await trader.check_resolutions()

        assert settled == 1
        trades = await paper_db.get_paper_trades(status="lost")
        assert len(trades) == 1
        assert trades[0]["pnl"] < 0

    async def test_settles_expired_converged_market(
        self, paper_db: Database,
    ) -> None:
        """Market not formally closed but end_date passed and prices converged."""
        from datetime import UTC, datetime, timedelta

        gamma = AsyncMock()
        gamma.get_market_detail.return_value = MarketDetail(
            condition_id="0xcond1",
            slug="will-x-happen",
            closed=False,
            active=True,
            end_date=datetime.now(UTC) - timedelta(hours=1),
            outcomes=["Yes", "No"],
            outcome_prices=[0.98, 0.02],
        )
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()
        await trader.on_alert(_make_alert(outcome="Yes"))

        settled = await trader.check_resolutions()

        assert settled == 1
        trades = await paper_db.get_paper_trades(status="won")
        assert len(trades) == 1

    async def test_skips_expired_unconverged_market(
        self, paper_db: Database,
    ) -> None:
        """Market past end_date but prices haven't converged — don't settle."""
        from datetime import UTC, datetime, timedelta

        gamma = AsyncMock()
        gamma.get_market_detail.return_value = MarketDetail(
            condition_id="0xcond1",
            slug="will-x-happen",
            closed=False,
            active=True,
            end_date=datetime.now(UTC) - timedelta(hours=1),
            outcomes=["Yes", "No"],
            outcome_prices=[0.60, 0.40],
        )
        trader = PaperTrader(paper_db, gamma_api=gamma)
        await trader.initialize()
        await trader.on_alert(_make_alert(outcome="Yes"))

        settled = await trader.check_resolutions()

        assert settled == 0


class TestDetermineWinner:
    def test_yes_wins(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[1.0, 0.0],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) == "Yes"

    def test_no_wins(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.0, 1.0],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) == "No"

    def test_no_outcomes(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=[],
            outcome_prices=[],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) is None

    def test_no_clear_winner(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.5, 0.5],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) is None

    def test_converged_price(self) -> None:
        """Prices at 0.95+ should be treated as a winner."""
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.96, 0.04],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) == "Yes"

    def test_near_converged_not_enough(self) -> None:
        """Prices at 0.90 should NOT be treated as a winner."""
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.90, 0.10],
            closed=True,
        )
        assert PaperTrader._determine_winner(market) is None


class TestPricesConverged:
    def test_converged(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.99, 0.01],
        )
        assert PaperTrader._prices_converged(market) is True

    def test_not_converged(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcomes=["Yes", "No"],
            outcome_prices=[0.60, 0.40],
        )
        assert PaperTrader._prices_converged(market) is False

    def test_empty_prices(self) -> None:
        market = MarketDetail(
            condition_id="x", slug="s",
            outcome_prices=[],
        )
        assert PaperTrader._prices_converged(market) is False
