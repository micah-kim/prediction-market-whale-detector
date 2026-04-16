"""Tests for SQLite database operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from whale_detector.db import Database
from whale_detector.models import Alert, ScoreResult, Trade

from conftest import make_trade_data


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    await database.initialize()
    yield database
    await database.close()


class TestDatabase:
    async def test_insert_and_exists(self, db: Database) -> None:
        trade = Trade.from_api(make_trade_data())
        assert await db.insert_trade(trade) is True
        assert await db.trade_exists(trade.transaction_hash) is True

    async def test_duplicate_insert(self, db: Database) -> None:
        trade = Trade.from_api(make_trade_data())
        assert await db.insert_trade(trade) is True
        assert await db.insert_trade(trade) is False

    async def test_trade_not_exists(self, db: Database) -> None:
        assert await db.trade_exists("nonexistent") is False

    async def test_latest_timestamp_empty(self, db: Database) -> None:
        assert await db.get_latest_timestamp() is None

    async def test_latest_timestamp(self, db: Database) -> None:
        t1 = Trade.from_api(make_trade_data(timestamp=1000, transactionHash="0x1"))
        t2 = Trade.from_api(make_trade_data(timestamp=2000, transactionHash="0x2"))
        await db.insert_trade(t1)
        await db.insert_trade(t2)
        assert await db.get_latest_timestamp() == 2000

    async def test_rolling_stats_insufficient_data(self, db: Database) -> None:
        trade = Trade.from_api(make_trade_data())
        await db.insert_trade(trade)
        stats = await db.get_rolling_stats(trade.condition_id)
        assert stats is None  # need at least 2 trades

    async def test_rolling_stats(self, db: Database) -> None:
        for i, size in enumerate([100.0, 200.0, 300.0, 400.0, 500.0]):
            trade = Trade.from_api(
                make_trade_data(
                    size=size,
                    price=1.0,
                    transactionHash=f"0xtx{i}",
                )
            )
            await db.insert_trade(trade)

        stats = await db.get_rolling_stats("0xcondition123")
        assert stats is not None
        assert stats.count == 5
        assert stats.mean == pytest.approx(300.0)
        assert stats.stddev > 0

    async def test_insert_alert(self, db: Database) -> None:
        trade = Trade.from_api(make_trade_data())
        await db.insert_trade(trade)

        alert = Alert(
            trade=trade,
            scores=[ScoreResult(scorer_name="test", score=0.9, reason="big")],
            composite_score=0.9,
        )
        await db.insert_alert(alert)

    async def test_wallet_trade_count(self, db: Database) -> None:
        wallet = "0xwallet1"
        for i in range(3):
            trade = Trade.from_api(
                make_trade_data(proxyWallet=wallet, transactionHash=f"0xtx{i}")
            )
            await db.insert_trade(trade)
        assert await db.get_wallet_trade_count(wallet) == 3
        assert await db.get_wallet_trade_count("0xother") == 0
