"""Tests for historical analysis DB queries and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from whale_detector.cli import main
from whale_detector.db import Database
from whale_detector.models import Alert, ScoreResult, Trade

from conftest import make_trade_data


@pytest.fixture
async def populated_db(tmp_path: Path) -> Database:
    """Database with sample trades and alerts."""
    db = Database(tmp_path / "test.db")
    await db.initialize()

    for i in range(15):
        t = Trade.from_api(make_trade_data(
            proxyWallet=f"0xwallet_{i % 5}",
            conditionId=f"0xmarket_{i % 3}",
            slug=f"market-{i % 3}",
            title=f"Market #{i % 3}",
            side="BUY" if i % 2 == 0 else "SELL",
            price=0.50,
            size=100.0 * (i + 1),
            timestamp=1700000000 + i * 100,
            transactionHash=f"0xhist_{i}",
        ))
        await db.insert_trade(t)

    # Insert an alert
    alert_trade = Trade.from_api(make_trade_data(
        size=20000.0, price=0.90,
        transactionHash="0xhist_0",  # matches existing trade
    ))
    alert = Alert(
        trade=alert_trade,
        scores=[ScoreResult(
            scorer_name="trade_size", score=1.0,
            reason="Exceeds threshold",
        )],
        composite_score=0.85,
    )
    await db.insert_alert(alert)

    yield db
    await db.close()


class TestGlobalStats:
    async def test_returns_stats(self, populated_db: Database) -> None:
        stats = await populated_db.get_global_stats()
        assert stats["total_trades"] == 15
        assert stats["unique_wallets"] == 5
        assert stats["unique_markets"] == 3
        assert stats["total_volume"] > 0
        assert stats["buys"] + stats["sells"] == 15

    async def test_empty_db(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "empty.db")
        await db.initialize()
        stats = await db.get_global_stats()
        assert stats == {}
        await db.close()


class TestAlertCount:
    async def test_counts_alerts(self, populated_db: Database) -> None:
        count = await populated_db.get_alert_count()
        assert count == 1

    async def test_empty_db(self, tmp_path: Path) -> None:
        db = Database(tmp_path / "empty.db")
        await db.initialize()
        assert await db.get_alert_count() == 0
        await db.close()


class TestTopMarkets:
    async def test_returns_ordered(self, populated_db: Database) -> None:
        markets = await populated_db.get_top_markets(3)
        assert len(markets) == 3
        # Should be ordered by volume descending
        vols = [m["total_volume"] for m in markets]
        assert vols == sorted(vols, reverse=True)

    async def test_respects_limit(self, populated_db: Database) -> None:
        markets = await populated_db.get_top_markets(1)
        assert len(markets) == 1


class TestTopWallets:
    async def test_returns_ordered(self, populated_db: Database) -> None:
        wallets = await populated_db.get_top_wallets(5)
        assert len(wallets) == 5
        vols = [w["total_volume"] for w in wallets]
        assert vols == sorted(vols, reverse=True)


class TestMarketTrades:
    async def test_returns_trades(self, populated_db: Database) -> None:
        trades = await populated_db.get_market_trades("market-0")
        assert len(trades) > 0
        assert all(t.slug == "market-0" for t in trades)

    async def test_unknown_slug(self, populated_db: Database) -> None:
        trades = await populated_db.get_market_trades("nonexistent")
        assert trades == []


class TestRecentAlerts:
    async def test_returns_alerts(self, populated_db: Database) -> None:
        alerts = await populated_db.get_recent_alerts(10)
        assert len(alerts) == 1
        assert alerts[0]["composite_score"] == 0.85
        assert alerts[0]["impact"] == "high"


class TestConfigInitCLI:
    def test_creates_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "test_config.toml"
        runner = CliRunner()
        result = runner.invoke(main, ["config", "init", "--path", str(dest)])
        assert result.exit_code == 0
        assert dest.exists()
        content = dest.read_text()
        assert "[general]" in content
        assert "[thresholds]" in content
        assert "[scoring]" in content

    def test_refuses_overwrite(self, tmp_path: Path) -> None:
        dest = tmp_path / "existing.toml"
        dest.write_text("existing")
        runner = CliRunner()
        result = runner.invoke(main, ["config", "init", "--path", str(dest)])
        assert result.exit_code != 0
