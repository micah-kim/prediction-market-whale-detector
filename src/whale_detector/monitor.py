"""Async trade monitoring loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import time
from typing import TYPE_CHECKING

from whale_detector.alerting.base import AlertSink
from whale_detector.api.data_api import DataAPI
from whale_detector.config import Settings
from whale_detector.coordination import CoordinatedEntryDetector
from whale_detector.db import Database
from whale_detector.models import Trade
from whale_detector.paper_trading import PaperTrader
from whale_detector.scoring.base import CompositeScorer, ScoringContext

if TYPE_CHECKING:
    from whale_detector.api.gamma_api import GammaAPI

logger = logging.getLogger(__name__)


class TradeMonitor:
    """Polls the Polymarket Data API for trades and scores them for anomalies."""

    def __init__(
        self,
        data_api: DataAPI,
        db: Database,
        scorer: CompositeScorer,
        sinks: list[AlertSink],
        settings: Settings,
        fresh_wallets_only: int | None = None,
        gamma_api: GammaAPI | None = None,
        coordination_detector: CoordinatedEntryDetector | None = None,
        coordination_interval: int = 300,
        paper_trader: PaperTrader | None = None,
        resolution_interval: int = 3600,
    ) -> None:
        self._data_api = data_api
        self._db = db
        self._scorer = scorer
        self._sinks = sinks
        self._settings = settings
        self._fresh_wallets_only = fresh_wallets_only
        self._stop = asyncio.Event()
        self._context = ScoringContext(db=db, gamma_api=gamma_api)
        self._coord_detector = coordination_detector
        self._coord_interval = coordination_interval
        self._last_coord_scan: float = 0.0
        self._paper_trader = paper_trader
        self._resolution_interval = resolution_interval
        self._last_resolution_check: float = 0.0

    async def run(self) -> None:
        """Main polling loop. Runs until SIGINT/SIGTERM."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._stop.set)

        logger.info(
            "Starting trade monitor (poll every %ds, threshold %.2f)",
            self._settings.poll_interval_seconds,
            self._settings.thresholds.alert_threshold,
        )

        last_timestamp = await self._db.get_latest_timestamp()

        while not self._stop.is_set():
            try:
                new_trades = await self._poll(last_timestamp)
                if new_trades:
                    latest = max(t.timestamp for t in new_trades)
                    last_timestamp = latest
                    logger.info("Processed %d new trades", len(new_trades))

                # Run coordination scan periodically
                await self._maybe_run_coordination_scan()

                # Check for resolved markets (paper trading)
                await self._maybe_check_resolutions()

            except Exception:
                logger.exception("Error during poll cycle")

            try:
                timeout = self._settings.poll_interval_seconds
                await asyncio.wait_for(
                    self._stop.wait(), timeout=timeout,
                )
                break  # stop was set
            except TimeoutError:
                pass  # normal: timeout means keep polling

        logger.info("Monitor stopped")

    async def _maybe_run_coordination_scan(self) -> None:
        """Run the coordination detector if enough time has passed."""
        if self._coord_detector is None:
            return

        now = time.time()
        if now - self._last_coord_scan < self._coord_interval:
            return

        self._last_coord_scan = now
        try:
            entries = await self._coord_detector.scan(self._db)
            self._context.coordinated_entries = entries
            if entries:
                logger.info(
                    "Coordination scan: %d pattern(s) detected",
                    len(entries),
                )
        except Exception:
            logger.exception("Error during coordination scan")

    async def _maybe_check_resolutions(self) -> None:
        """Check for resolved markets and settle paper trades."""
        if self._paper_trader is None:
            return

        now = time.time()
        if now - self._last_resolution_check < self._resolution_interval:
            return

        self._last_resolution_check = now
        try:
            settled = await self._paper_trader.check_resolutions()
            if settled:
                logger.info(
                    "Resolution check: settled %d paper trade(s)",
                    settled,
                )
        except Exception:
            logger.exception("Error during resolution check")

    async def _poll(self, after_timestamp: int | None) -> list[Trade]:
        """Fetch, deduplicate, persist, score, and alert on new trades."""
        trades = await self._data_api.get_recent_trades(
            limit=100, after_timestamp=after_timestamp
        )

        new_trades: list[Trade] = []
        for trade in trades:
            if not trade.transaction_hash:
                continue
            if await self._db.trade_exists(trade.transaction_hash):
                continue
            if not await self._db.insert_trade(trade):
                continue
            new_trades.append(trade)

        for trade in new_trades:
            if self._fresh_wallets_only is not None:
                count = await self._db.get_wallet_trade_count(trade.proxy_wallet)
                if count > self._fresh_wallets_only:
                    continue

            alert = await self._scorer.evaluate(
                trade, self._context, self._settings.thresholds.alert_threshold
            )
            if alert:
                await self._db.insert_alert(alert)
                for sink in self._sinks:
                    try:
                        await sink.send(alert)
                    except Exception:
                        logger.exception(
                            "Error sending alert via %s",
                            type(sink).__name__,
                        )
                if self._paper_trader:
                    try:
                        await self._paper_trader.on_alert(alert)
                    except Exception:
                        logger.exception("Error creating paper trade")

        return new_trades
