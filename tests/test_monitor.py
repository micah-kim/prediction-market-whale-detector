"""Tests for the trade monitor."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from whale_detector.config import Settings
from whale_detector.db import Database
from whale_detector.models import Alert, ScoreResult, Trade
from whale_detector.monitor import TradeMonitor
from whale_detector.scoring.base import CompositeScorer, ScoringContext
from whale_detector.scoring.trade_size import TradeSizeScorer

from conftest import make_trade_data


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def settings() -> Settings:
    return Settings()


class TestTradeMonitor:
    async def test_deduplicates_trades(self, db: Database, settings: Settings) -> None:
        data_api = AsyncMock()
        trade = Trade.from_api(make_trade_data())
        data_api.get_recent_trades.return_value = [trade, trade]

        scorer = CompositeScorer([(TradeSizeScorer(), 1.0)])
        sink = AsyncMock()

        monitor = TradeMonitor(
            data_api=data_api, db=db, scorer=scorer, sinks=[sink], settings=settings
        )

        new = await monitor._poll(None)
        assert len(new) == 1
        assert await db.trade_exists(trade.transaction_hash)

    async def test_fires_alert_on_whale(self, db: Database, settings: Settings) -> None:
        data_api = AsyncMock()
        whale = Trade.from_api(
            make_trade_data(size=50_000.0, price=0.90, transactionHash="0xwhale")
        )
        data_api.get_recent_trades.return_value = [whale]

        scorer = CompositeScorer(
            [(TradeSizeScorer(absolute_threshold=10_000), 1.0)]
        )
        sink = AsyncMock()

        monitor = TradeMonitor(
            data_api=data_api, db=db, scorer=scorer, sinks=[sink],
            settings=Settings(thresholds={"alert_threshold": 0.5}),
        )

        await monitor._poll(None)
        sink.send.assert_called_once()
        alert = sink.send.call_args[0][0]
        assert isinstance(alert, Alert)
        assert alert.composite_score >= 0.5

    async def test_no_alert_for_small_trade(self, db: Database, settings: Settings) -> None:
        data_api = AsyncMock()
        small = Trade.from_api(make_trade_data(size=10.0, price=0.50))
        data_api.get_recent_trades.return_value = [small]

        scorer = CompositeScorer(
            [(TradeSizeScorer(absolute_threshold=10_000), 1.0)]
        )
        sink = AsyncMock()

        monitor = TradeMonitor(
            data_api=data_api, db=db, scorer=scorer, sinks=[sink], settings=settings
        )

        await monitor._poll(None)
        sink.send.assert_not_called()

    async def test_fresh_wallets_filter(self, db: Database, settings: Settings) -> None:
        # Pre-populate the wallet with many trades
        for i in range(10):
            trade = Trade.from_api(
                make_trade_data(
                    proxyWallet="0xold_wallet",
                    size=50_000.0,
                    price=0.90,
                    transactionHash=f"0xold{i}",
                )
            )
            await db.insert_trade(trade)

        data_api = AsyncMock()
        new_trade = Trade.from_api(
            make_trade_data(
                proxyWallet="0xold_wallet",
                size=50_000.0,
                price=0.90,
                transactionHash="0xnew_from_old",
            )
        )
        data_api.get_recent_trades.return_value = [new_trade]

        scorer = CompositeScorer(
            [(TradeSizeScorer(absolute_threshold=10_000), 1.0)]
        )
        sink = AsyncMock()

        monitor = TradeMonitor(
            data_api=data_api, db=db, scorer=scorer, sinks=[sink],
            settings=Settings(thresholds={"alert_threshold": 0.5}),
            fresh_wallets_only=5,
        )

        await monitor._poll(None)
        sink.send.assert_not_called()  # wallet has > 5 trades, filtered out
