"""Coordination scorer — boosts trades from wallets in coordinated entry patterns."""

from __future__ import annotations

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


class CoordinationScorer:
    """Scores a trade based on whether its wallet is part of a detected
    coordinated entry pattern.

    This scorer does not run its own detection — it consumes results from
    the ``CoordinatedEntryDetector``, which runs periodically in the
    monitor loop. The detected entries are stored on the ``ScoringContext``
    and looked up here by wallet address.

    Score is the confidence of the coordinated entry the wallet belongs to.
    """

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return "coordination"

    async def score(
        self, trade: Trade, context: ScoringContext,
    ) -> ScoreResult:
        entries = getattr(context, "coordinated_entries", None)
        if not entries:
            return ScoreResult(scorer_name=self.name, score=0.0)

        # Check if this trade's wallet is in any detected coordinated entry
        for entry in entries:
            if trade.proxy_wallet in entry.wallets:
                return ScoreResult(
                    scorer_name=self.name,
                    score=entry.confidence,
                    reason=(
                        f"Wallet part of coordinated entry: "
                        f"{len(entry.wallets)} wallets, "
                        f"{entry.fresh_wallet_count} fresh, "
                        f"${entry.total_usdc:,.0f} total, "
                        f"avg price {entry.avg_price:.1%} "
                        f"in {entry.market_title or entry.condition_id[:12]}"
                    ),
                )

        return ScoreResult(scorer_name=self.name, score=0.0)
