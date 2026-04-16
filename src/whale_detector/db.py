"""SQLite persistence for trades, alerts, and rolling statistics."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from whale_detector.models import Alert, RollingStats, Trade, WalletProfile

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_hash TEXT UNIQUE NOT NULL,
    proxy_wallet TEXT NOT NULL,
    side TEXT NOT NULL,
    asset TEXT,
    condition_id TEXT NOT NULL,
    size REAL NOT NULL,
    price REAL NOT NULL,
    usdc_value REAL NOT NULL,
    timestamp INTEGER NOT NULL,
    title TEXT,
    slug TEXT,
    event_slug TEXT,
    outcome TEXT,
    outcome_index INTEGER,
    pseudonym TEXT,
    inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_condition_id ON trades(condition_id);
CREATE INDEX IF NOT EXISTS idx_trades_proxy_wallet ON trades(proxy_wallet);
CREATE INDEX IF NOT EXISTS idx_trades_slug ON trades(slug);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_hash TEXT NOT NULL,
    composite_score REAL NOT NULL,
    impact TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_hash) REFERENCES trades(transaction_hash)
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at);
"""


class Database:
    """Async SQLite database for trade and alert persistence."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        """Create the database file and tables."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()
        logger.info("Database initialized at %s", self._db_path)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    async def trade_exists(self, transaction_hash: str) -> bool:
        """Check if a trade with this transaction hash already exists."""
        cursor = await self.conn.execute(
            "SELECT 1 FROM trades WHERE transaction_hash = ?",
            (transaction_hash,),
        )
        return await cursor.fetchone() is not None

    async def insert_trade(self, trade: Trade) -> bool:
        """Insert a trade, returning True if inserted, False if duplicate."""
        try:
            await self.conn.execute(
                """INSERT INTO trades (
                    transaction_hash, proxy_wallet, side, asset, condition_id,
                    size, price, usdc_value, timestamp, title, slug, event_slug,
                    outcome, outcome_index, pseudonym
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.transaction_hash,
                    trade.proxy_wallet,
                    trade.side,
                    trade.asset,
                    trade.condition_id,
                    trade.size,
                    trade.price,
                    trade.usdc_value,
                    trade.timestamp,
                    trade.title,
                    trade.slug,
                    trade.event_slug,
                    trade.outcome,
                    trade.outcome_index,
                    trade.pseudonym,
                ),
            )
            await self.conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

    async def get_rolling_stats(
        self, condition_id: str, window: int = 500
    ) -> RollingStats | None:
        """Get rolling mean and stddev of usdc_value for a market.

        Returns None if there are fewer than 2 trades for the market.
        """
        cursor = await self.conn.execute(
            """SELECT AVG(usdc_value), COUNT(usdc_value)
            FROM (
                SELECT usdc_value FROM trades
                WHERE condition_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )""",
            (condition_id, window),
        )
        row = await cursor.fetchone()
        if row is None or row[1] < 2:
            return None

        mean, count = float(row[0]), int(row[1])

        # Compute stddev
        cursor = await self.conn.execute(
            """SELECT AVG((usdc_value - ?) * (usdc_value - ?))
            FROM (
                SELECT usdc_value FROM trades
                WHERE condition_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            )""",
            (mean, mean, condition_id, window),
        )
        var_row = await cursor.fetchone()
        variance = float(var_row[0]) if var_row and var_row[0] else 0.0
        stddev = variance**0.5

        return RollingStats(mean=mean, stddev=stddev, count=count)

    async def get_latest_timestamp(self) -> int | None:
        """Get the timestamp of the most recent trade in the database."""
        cursor = await self.conn.execute(
            "SELECT MAX(timestamp) FROM trades"
        )
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None

    async def insert_alert(self, alert: Alert) -> None:
        """Persist an alert to the database."""
        scores_json = json.dumps([
            {"name": s.scorer_name, "score": s.score, "reason": s.reason}
            for s in alert.scores
        ])
        reasons_json = json.dumps(alert.reasons)

        await self.conn.execute(
            """INSERT INTO alerts (
                transaction_hash, composite_score, impact, scores_json, reasons_json
            ) VALUES (?, ?, ?, ?, ?)""",
            (
                alert.trade.transaction_hash,
                alert.composite_score,
                alert.impact.value,
                scores_json,
                reasons_json,
            ),
        )
        await self.conn.commit()

    async def get_wallet_trade_count(self, proxy_wallet: str) -> int:
        """Count total trades for a wallet."""
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM trades WHERE proxy_wallet = ?",
            (proxy_wallet,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_wallet_profile(
        self, proxy_wallet: str,
    ) -> WalletProfile:
        """Build a wallet profile from stored trades."""
        cursor = await self.conn.execute(
            """SELECT
                COUNT(*) as total_trades,
                COUNT(DISTINCT condition_id) as unique_markets,
                SUM(usdc_value) as total_volume,
                MIN(timestamp) as first_seen,
                MAX(timestamp) as last_seen,
                SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) as sells
            FROM trades WHERE proxy_wallet = ?""",
            (proxy_wallet,),
        )
        row = await cursor.fetchone()

        if not row or row[0] == 0:
            return WalletProfile(address=proxy_wallet)

        from datetime import UTC, datetime

        first_seen = (
            datetime.fromtimestamp(row[3], tz=UTC) if row[3] else None
        )
        last_seen = (
            datetime.fromtimestamp(row[4], tz=UTC) if row[4] else None
        )

        # Get pseudonym from most recent trade
        cursor2 = await self.conn.execute(
            """SELECT pseudonym FROM trades
            WHERE proxy_wallet = ? AND pseudonym != ''
            ORDER BY timestamp DESC LIMIT 1""",
            (proxy_wallet,),
        )
        pseudo_row = await cursor2.fetchone()
        pseudonym = pseudo_row[0] if pseudo_row else ""

        return WalletProfile(
            address=proxy_wallet,
            first_seen=first_seen,
            last_seen=last_seen,
            total_trades=int(row[0]),
            unique_markets=int(row[1]),
            total_usdc_volume=float(row[2] or 0),
            buy_count=int(row[5] or 0),
            sell_count=int(row[6] or 0),
            pseudonym=pseudonym,
        )

    async def get_wallet_first_seen(
        self, proxy_wallet: str,
    ) -> int | None:
        """Get the timestamp of the wallet's earliest trade."""
        cursor = await self.conn.execute(
            "SELECT MIN(timestamp) FROM trades WHERE proxy_wallet = ?",
            (proxy_wallet,),
        )
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return int(row[0])
        return None

    async def get_wallet_unique_markets(
        self, proxy_wallet: str,
    ) -> int:
        """Count distinct markets a wallet has traded in."""
        cursor = await self.conn.execute(
            """SELECT COUNT(DISTINCT condition_id)
            FROM trades WHERE proxy_wallet = ?""",
            (proxy_wallet,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_recent_market_entries(
        self,
        condition_id: str,
        since_timestamp: int,
        side: str = "BUY",
        max_price: float = 0.20,
    ) -> list[Trade]:
        """Get trades matching a market + side + price filter in a time window.

        Used by the coordination detector to find bursts of minority-side
        entries in a specific market.
        """
        cursor = await self.conn.execute(
            """SELECT
                transaction_hash, proxy_wallet, side, asset, condition_id,
                size, price, usdc_value, timestamp, title, slug, event_slug,
                outcome, outcome_index, pseudonym
            FROM trades
            WHERE condition_id = ?
              AND timestamp >= ?
              AND side = ?
              AND price <= ?
            ORDER BY timestamp ASC""",
            (condition_id, since_timestamp, side, max_price),
        )
        rows = await cursor.fetchall()
        trades: list[Trade] = []
        for r in rows:
            trades.append(Trade(
                transaction_hash=r[0],
                proxy_wallet=r[1],
                side=r[2],
                asset=r[3] or "",
                condition_id=r[4],
                size=r[5],
                price=r[6],
                timestamp=r[8],
                title=r[9] or "",
                slug=r[10] or "",
                event_slug=r[11] or "",
                outcome=r[12] or "",
                outcome_index=r[13] or 0,
                pseudonym=r[14] or "",
            ))
        return trades

    async def get_active_minority_markets(
        self,
        since_timestamp: int,
        max_price: float = 0.20,
        min_wallets: int = 3,
    ) -> list[str]:
        """Find markets with recent minority-side BUY activity from multiple wallets.

        Returns condition_ids where at least ``min_wallets`` distinct wallets
        bought below ``max_price`` since ``since_timestamp``.
        """
        cursor = await self.conn.execute(
            """SELECT condition_id
            FROM trades
            WHERE timestamp >= ?
              AND side = 'BUY'
              AND price <= ?
            GROUP BY condition_id
            HAVING COUNT(DISTINCT proxy_wallet) >= ?""",
            (since_timestamp, max_price, min_wallets),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_wallet_trade_counts_batch(
        self, wallets: list[str],
    ) -> dict[str, int]:
        """Get trade counts for multiple wallets in one query."""
        if not wallets:
            return {}
        placeholders = ",".join("?" for _ in wallets)
        cursor = await self.conn.execute(
            f"""SELECT proxy_wallet, COUNT(*)
            FROM trades
            WHERE proxy_wallet IN ({placeholders})
            GROUP BY proxy_wallet""",
            wallets,
        )
        rows = await cursor.fetchall()
        return {r[0]: int(r[1]) for r in rows}

    async def get_global_stats(self) -> dict[str, Any]:
        """Get aggregate statistics across all stored data."""
        cursor = await self.conn.execute(
            """SELECT
                COUNT(*) as total_trades,
                COUNT(DISTINCT proxy_wallet) as unique_wallets,
                COUNT(DISTINCT condition_id) as unique_markets,
                SUM(usdc_value) as total_volume,
                MIN(timestamp) as first_trade,
                MAX(timestamp) as last_trade,
                AVG(usdc_value) as avg_trade_size,
                SUM(CASE WHEN side = 'BUY' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side = 'SELL' THEN 1 ELSE 0 END) as sells
            FROM trades"""
        )
        row = await cursor.fetchone()
        if not row or row[0] == 0:
            return {}

        return {
            "total_trades": int(row[0]),
            "unique_wallets": int(row[1]),
            "unique_markets": int(row[2]),
            "total_volume": float(row[3] or 0),
            "first_trade": int(row[4]) if row[4] else None,
            "last_trade": int(row[5]) if row[5] else None,
            "avg_trade_size": float(row[6] or 0),
            "buys": int(row[7] or 0),
            "sells": int(row[8] or 0),
        }

    async def get_alert_count(self) -> int:
        """Count total alerts in the database."""
        cursor = await self.conn.execute("SELECT COUNT(*) FROM alerts")
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def get_top_markets(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get markets with the most trades."""
        cursor = await self.conn.execute(
            """SELECT
                condition_id,
                COALESCE(title, slug, condition_id) as market_name,
                COUNT(*) as trade_count,
                COUNT(DISTINCT proxy_wallet) as unique_wallets,
                SUM(usdc_value) as total_volume
            FROM trades
            GROUP BY condition_id
            ORDER BY total_volume DESC
            LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "condition_id": r[0],
                "market_name": r[1],
                "trade_count": int(r[2]),
                "unique_wallets": int(r[3]),
                "total_volume": float(r[4] or 0),
            }
            for r in rows
        ]

    async def get_top_wallets(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get wallets with the highest USDC volume."""
        cursor = await self.conn.execute(
            """SELECT
                proxy_wallet,
                COALESCE(MAX(pseudonym), '') as pseudonym,
                COUNT(*) as trade_count,
                COUNT(DISTINCT condition_id) as unique_markets,
                SUM(usdc_value) as total_volume
            FROM trades
            GROUP BY proxy_wallet
            ORDER BY total_volume DESC
            LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "proxy_wallet": r[0],
                "pseudonym": r[1],
                "trade_count": int(r[2]),
                "unique_markets": int(r[3]),
                "total_volume": float(r[4] or 0),
            }
            for r in rows
        ]

    async def get_market_trades(
        self,
        slug: str,
        limit: int = 50,
    ) -> list[Trade]:
        """Get recent trades for a specific market by slug."""
        cursor = await self.conn.execute(
            """SELECT
                transaction_hash, proxy_wallet, side, asset, condition_id,
                size, price, usdc_value, timestamp, title, slug, event_slug,
                outcome, outcome_index, pseudonym
            FROM trades
            WHERE slug = ?
            ORDER BY timestamp DESC
            LIMIT ?""",
            (slug, limit),
        )
        return self._rows_to_trades(await cursor.fetchall())

    async def get_recent_trades_all(
        self, limit: int = 50,
    ) -> list[Trade]:
        """Get the most recent trades across all markets."""
        cursor = await self.conn.execute(
            """SELECT
                transaction_hash, proxy_wallet, side, asset, condition_id,
                size, price, usdc_value, timestamp, title, slug, event_slug,
                outcome, outcome_index, pseudonym
            FROM trades
            ORDER BY timestamp DESC
            LIMIT ?""",
            (limit,),
        )
        return self._rows_to_trades(await cursor.fetchall())

    def _rows_to_trades(self, rows: list) -> list[Trade]:
        """Convert raw DB rows into Trade objects."""
        trades: list[Trade] = []
        for r in rows:
            trades.append(Trade(
                transaction_hash=r[0],
                proxy_wallet=r[1],
                side=r[2],
                asset=r[3] or "",
                condition_id=r[4],
                size=r[5],
                price=r[6],
                timestamp=r[8],
                title=r[9] or "",
                slug=r[10] or "",
                event_slug=r[11] or "",
                outcome=r[12] or "",
                outcome_index=r[13] or 0,
                pseudonym=r[14] or "",
            ))
        return trades

    async def get_recent_alerts(
        self, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get recent alerts with associated trade info."""
        cursor = await self.conn.execute(
            """SELECT
                a.composite_score, a.impact, a.scores_json,
                a.reasons_json, a.created_at,
                t.title, t.slug, t.outcome, t.side,
                t.usdc_value, t.proxy_wallet, t.pseudonym
            FROM alerts a
            JOIN trades t ON a.transaction_hash = t.transaction_hash
            ORDER BY a.created_at DESC
            LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "composite_score": float(r[0]),
                "impact": r[1],
                "scores_json": r[2],
                "reasons_json": r[3],
                "created_at": r[4],
                "title": r[5] or "",
                "slug": r[6] or "",
                "outcome": r[7] or "",
                "side": r[8] or "",
                "usdc_value": float(r[9] or 0),
                "proxy_wallet": r[10] or "",
                "pseudonym": r[11] or "",
            }
            for r in rows
        ]

    # --- Paper Trading ---

    _PAPER_SCHEMA = """
    CREATE TABLE IF NOT EXISTS paper_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT NOT NULL,
        condition_id TEXT NOT NULL,
        market_slug TEXT,
        market_title TEXT,
        outcome TEXT NOT NULL,
        side TEXT NOT NULL DEFAULT 'BUY',
        entry_price REAL NOT NULL,
        shares REAL NOT NULL,
        cost_basis REAL NOT NULL,
        exit_price REAL,
        pnl REAL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        whale_score REAL NOT NULL,
        whale_wallet TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_paper_trades_status
        ON paper_trades(status);
    CREATE INDEX IF NOT EXISTS idx_paper_trades_condition
        ON paper_trades(condition_id);

    CREATE TABLE IF NOT EXISTS paper_bankroll (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        initial_bankroll REAL NOT NULL,
        current_bankroll REAL NOT NULL,
        total_deployed REAL NOT NULL DEFAULT 0.0,
        total_realized_pnl REAL NOT NULL DEFAULT 0.0
    );
    """

    async def initialize_paper_trading(
        self, initial_bankroll: float,
    ) -> None:
        """Create paper trading tables and seed bankroll if needed."""
        await self.conn.executescript(self._PAPER_SCHEMA)
        await self.conn.commit()

        cursor = await self.conn.execute(
            "SELECT 1 FROM paper_bankroll WHERE id = 1"
        )
        if await cursor.fetchone() is None:
            await self.conn.execute(
                """INSERT INTO paper_bankroll
                    (id, initial_bankroll, current_bankroll)
                VALUES (1, ?, ?)""",
                (initial_bankroll, initial_bankroll),
            )
            await self.conn.commit()

    async def get_paper_bankroll(self) -> dict[str, Any] | None:
        """Get the paper trading bankroll state."""
        cursor = await self.conn.execute(
            """SELECT initial_bankroll, current_bankroll,
                      total_deployed, total_realized_pnl
            FROM paper_bankroll WHERE id = 1"""
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "initial_bankroll": float(row[0]),
            "current_bankroll": float(row[1]),
            "total_deployed": float(row[2]),
            "total_realized_pnl": float(row[3]),
        }

    async def insert_paper_trade(
        self,
        alert_id: str,
        condition_id: str,
        market_slug: str,
        market_title: str,
        outcome: str,
        entry_price: float,
        shares: float,
        cost_basis: float,
        whale_score: float,
        whale_wallet: str,
    ) -> None:
        """Insert a new paper trade."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        await self.conn.execute(
            """INSERT INTO paper_trades (
                alert_id, condition_id, market_slug, market_title,
                outcome, entry_price, shares, cost_basis,
                whale_score, whale_wallet, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert_id, condition_id, market_slug, market_title,
                outcome, entry_price, shares, cost_basis,
                whale_score, whale_wallet, now,
            ),
        )
        await self.conn.commit()

    async def update_paper_bankroll(
        self,
        current_bankroll: float,
        total_deployed_delta: float = 0.0,
        realized_pnl_delta: float = 0.0,
    ) -> None:
        """Update the paper bankroll."""
        await self.conn.execute(
            """UPDATE paper_bankroll SET
                current_bankroll = ?,
                total_deployed = total_deployed + ?,
                total_realized_pnl = total_realized_pnl + ?
            WHERE id = 1""",
            (current_bankroll, total_deployed_delta, realized_pnl_delta),
        )
        await self.conn.commit()

    async def get_paper_trades(
        self, status: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get paper trades, optionally filtered by status."""
        if status:
            cursor = await self.conn.execute(
                """SELECT id, alert_id, condition_id, market_slug,
                          market_title, outcome, side, entry_price,
                          shares, cost_basis, exit_price, pnl,
                          status, created_at, resolved_at,
                          whale_score, whale_wallet
                FROM paper_trades WHERE status = ?
                ORDER BY created_at DESC LIMIT ?""",
                (status, limit),
            )
        else:
            cursor = await self.conn.execute(
                """SELECT id, alert_id, condition_id, market_slug,
                          market_title, outcome, side, entry_price,
                          shares, cost_basis, exit_price, pnl,
                          status, created_at, resolved_at,
                          whale_score, whale_wallet
                FROM paper_trades
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "alert_id": r[1],
                "condition_id": r[2],
                "market_slug": r[3] or "",
                "market_title": r[4] or "",
                "outcome": r[5],
                "side": r[6],
                "entry_price": float(r[7]),
                "shares": float(r[8]),
                "cost_basis": float(r[9]),
                "exit_price": float(r[10]) if r[10] is not None else None,
                "pnl": float(r[11]) if r[11] is not None else None,
                "status": r[12],
                "created_at": r[13],
                "resolved_at": r[14],
                "whale_score": float(r[15]),
                "whale_wallet": r[16],
            }
            for r in rows
        ]

    async def get_open_paper_trade_condition_ids(self) -> list[str]:
        """Get distinct condition_ids that have open paper trades."""
        cursor = await self.conn.execute(
            "SELECT DISTINCT condition_id FROM paper_trades WHERE status = 'open'"
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_open_paper_trade_slugs(self) -> list[dict[str, str]]:
        """Get distinct slugs with their condition_ids from open paper trades."""
        cursor = await self.conn.execute(
            """SELECT DISTINCT market_slug, condition_id
            FROM paper_trades WHERE status = 'open' AND market_slug != ''"""
        )
        rows = await cursor.fetchall()
        return [{"slug": r[0], "condition_id": r[1]} for r in rows]

    async def get_open_paper_trades(
        self, condition_id: str,
    ) -> list[dict[str, Any]]:
        """Get open paper trades for a specific market."""
        cursor = await self.conn.execute(
            """SELECT id, outcome, entry_price, shares, cost_basis
            FROM paper_trades
            WHERE condition_id = ? AND status = 'open'""",
            (condition_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0],
                "outcome": r[1],
                "entry_price": float(r[2]),
                "shares": float(r[3]),
                "cost_basis": float(r[4]),
            }
            for r in rows
        ]

    async def settle_paper_trade(
        self,
        trade_id: int,
        exit_price: float,
        pnl: float,
        status: str,
        resolved_at: str,
    ) -> None:
        """Settle a paper trade with exit price and PnL."""
        await self.conn.execute(
            """UPDATE paper_trades SET
                exit_price = ?, pnl = ?, status = ?, resolved_at = ?
            WHERE id = ?""",
            (exit_price, pnl, status, resolved_at, trade_id),
        )
        await self.conn.commit()

    async def get_paper_summary(self) -> dict[str, Any]:
        """Get paper trading summary statistics."""
        bankroll = await self.get_paper_bankroll()
        if not bankroll:
            return {}

        cursor = await self.conn.execute(
            """SELECT
                COUNT(*) FILTER (WHERE status = 'open') as open_count,
                COUNT(*) FILTER (WHERE status = 'won') as won_count,
                COUNT(*) FILTER (WHERE status = 'lost') as lost_count,
                COUNT(*) as total_count,
                AVG(whale_score) FILTER (WHERE status = 'won')
                    as avg_score_winners,
                AVG(whale_score) FILTER (WHERE status = 'lost')
                    as avg_score_losers
            FROM paper_trades"""
        )
        row = await cursor.fetchone()

        open_count = int(row[0]) if row else 0
        won = int(row[1]) if row else 0
        lost = int(row[2]) if row else 0
        total = int(row[3]) if row else 0
        closed = won + lost
        win_rate = won / closed if closed > 0 else 0.0
        roi = (
            bankroll["total_realized_pnl"] / bankroll["initial_bankroll"]
            if bankroll["initial_bankroll"] > 0
            else 0.0
        )

        return {
            **bankroll,
            "open_positions": open_count,
            "won": won,
            "lost": lost,
            "total_trades": total,
            "win_rate": win_rate,
            "roi": roi,
            "avg_score_winners": (
                float(row[4]) if row and row[4] else None
            ),
            "avg_score_losers": (
                float(row[5]) if row and row[5] else None
            ),
        }

    async def reset_paper_trading(
        self, initial_bankroll: float,
    ) -> None:
        """Reset all paper trading data."""
        await self.conn.execute("DELETE FROM paper_trades")
        await self.conn.execute(
            """UPDATE paper_bankroll SET
                current_bankroll = ?,
                total_deployed = 0.0,
                total_realized_pnl = 0.0
            WHERE id = 1""",
            (initial_bankroll,),
        )
        await self.conn.commit()
