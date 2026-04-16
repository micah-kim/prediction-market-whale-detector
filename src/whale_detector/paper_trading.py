"""Paper trading — auto-follow whale alerts with simulated positions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from whale_detector.db import Database
from whale_detector.models import Alert

if TYPE_CHECKING:
    from whale_detector.api.gamma_api import GammaAPI

logger = logging.getLogger(__name__)


class PaperTrader:
    """Creates simulated positions from whale alerts and tracks outcomes."""

    def __init__(
        self,
        db: Database,
        initial_bankroll: float = 10_000.0,
        risk_per_trade_pct: float = 0.02,
        min_alert_score: float = 0.5,
        gamma_api: GammaAPI | None = None,
    ) -> None:
        self._db = db
        self._initial_bankroll = initial_bankroll
        self._risk_pct = risk_per_trade_pct
        self._min_score = min_alert_score
        self._gamma_api = gamma_api

    async def initialize(self) -> None:
        """Ensure paper trading tables exist and bankroll is seeded."""
        await self._db.initialize_paper_trading(self._initial_bankroll)

    async def on_alert(self, alert: Alert) -> bool:
        """Create a paper trade from a whale alert.

        Returns True if a paper trade was created.
        """
        if alert.composite_score < self._min_score:
            return False

        trade = alert.trade
        if trade.side != "BUY":
            return False

        bankroll = await self._db.get_paper_bankroll()
        if not bankroll:
            return False

        current = bankroll["current_bankroll"]
        risk_amount = current * self._risk_pct
        if risk_amount <= 0 or trade.price <= 0:
            return False

        shares = risk_amount / trade.price
        cost_basis = shares * trade.price

        await self._db.insert_paper_trade(
            alert_id=trade.transaction_hash,
            condition_id=trade.condition_id,
            market_slug=trade.slug,
            market_title=trade.title,
            outcome=trade.outcome,
            entry_price=trade.price,
            shares=shares,
            cost_basis=cost_basis,
            whale_score=alert.composite_score,
            whale_wallet=trade.proxy_wallet,
        )

        await self._db.update_paper_bankroll(
            current_bankroll=current - cost_basis,
            total_deployed_delta=cost_basis,
        )

        logger.info(
            "Paper trade: %s shares of %s @ $%.3f ($%.2f)",
            f"{shares:.0f}",
            trade.outcome,
            trade.price,
            cost_basis,
        )
        return True

    async def settle_market(
        self,
        condition_id: str,
        winning_outcome: str,
    ) -> int:
        """Settle all open paper trades for a resolved market.

        Returns the number of trades settled.
        """
        trades = await self._db.get_open_paper_trades(condition_id)
        if not trades:
            return 0

        now = datetime.now(UTC).isoformat()
        settled = 0
        bankroll = await self._db.get_paper_bankroll()
        current = bankroll["current_bankroll"] if bankroll else 0
        deployed_delta = 0.0
        pnl_delta = 0.0

        for pt in trades:
            won = pt["outcome"] == winning_outcome
            exit_price = 1.0 if won else 0.0
            pnl = (exit_price - pt["entry_price"]) * pt["shares"]
            status = "won" if won else "lost"

            await self._db.settle_paper_trade(
                trade_id=pt["id"],
                exit_price=exit_price,
                pnl=pnl,
                status=status,
                resolved_at=now,
            )

            deployed_delta -= pt["cost_basis"]
            pnl_delta += pnl
            settled += 1

        # Return cost basis + pnl to bankroll
        returned = sum(t["cost_basis"] for t in trades) + pnl_delta
        await self._db.update_paper_bankroll(
            current_bankroll=current + returned,
            total_deployed_delta=deployed_delta,
            realized_pnl_delta=pnl_delta,
        )

        logger.info(
            "Settled %d paper trades for market %s (PnL: $%.2f)",
            settled,
            condition_id[:12],
            pnl_delta,
        )
        return settled

    async def check_resolutions(self) -> int:
        """Check all open paper trade markets for resolution via Gamma API.

        Settles when:
        - Market is formally closed (closed=True), OR
        - Market end_date has passed AND prices have converged (>= 0.95)

        Returns total number of trades settled.
        """
        if not self._gamma_api:
            return 0

        slug_entries = await self._db.get_open_paper_trade_slugs()
        if not slug_entries:
            return 0

        # Deduplicate slugs
        seen_slugs: dict[str, str] = {}  # slug -> condition_id
        for entry in slug_entries:
            seen_slugs[entry["slug"]] = entry["condition_id"]

        now = datetime.now(UTC)
        total_settled = 0
        for slug, condition_id in seen_slugs.items():
            try:
                market = await self._gamma_api.get_market_detail(slug)

                # Fallback to CLOB API for micro-markets not in Gamma
                if not market:
                    market = await self._gamma_api.get_market_from_clob(
                        condition_id,
                    )

                if not market:
                    continue

                # Check if market is formally closed
                is_resolved = market.closed

                # Also treat as resolved if end_date passed and
                # prices have converged (one outcome >= 0.95)
                if (
                    not is_resolved
                    and market.end_date
                    and market.end_date < now
                    and self._prices_converged(market)
                ):
                    is_resolved = True
                    logger.info(
                        "Market %s past end date with converged prices, "
                        "treating as resolved",
                        slug,
                    )

                if not is_resolved:
                    continue

                # Determine winning outcome from outcome_prices
                winning_outcome = self._determine_winner(market)
                if not winning_outcome:
                    logger.warning(
                        "Market %s resolved but cannot determine winner "
                        "(outcomes=%s, prices=%s)",
                        slug,
                        market.outcomes,
                        market.outcome_prices,
                    )
                    continue

                settled = await self.settle_market(
                    condition_id, winning_outcome,
                )
                total_settled += settled

            except Exception:
                logger.exception(
                    "Error checking resolution for %s", slug,
                )

        if total_settled > 0:
            logger.info(
                "Resolution check: settled %d paper trade(s) across %d market(s)",
                total_settled,
                len(seen_slugs),
            )

        return total_settled

    @staticmethod
    def _prices_converged(market) -> bool:
        """Check if any outcome price has converged to >= 0.95."""
        if not market.outcome_prices:
            return False
        return any(p >= 0.95 for p in market.outcome_prices)

    @staticmethod
    def _determine_winner(market) -> str | None:
        """Determine the winning outcome from a resolved market.

        When a binary market resolves, the winning outcome's price
        goes to 1.0 and the loser to 0.0. We use >= 0.95 as the
        threshold to handle near-converged markets.
        """
        if not market.outcomes or not market.outcome_prices:
            return None
        if len(market.outcomes) != len(market.outcome_prices):
            return None

        for outcome, price in zip(market.outcomes, market.outcome_prices, strict=False):
            if price >= 0.95:
                return outcome

        return None
