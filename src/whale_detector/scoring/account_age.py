"""Account age scorer — flags new or low-activity wallets."""

from __future__ import annotations

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


class AccountAgeScorer:
    """Detects fresh, single-purpose wallets that may indicate insider activity.

    Scores based on:
    - Wallet age (how recently the first trade appeared)
    - Total trade count (low activity)
    - Market diversity (single-market wallets are suspicious)
    """

    def __init__(
        self,
        new_wallet_days: float = 7.0,
        min_trades_for_established: int = 10,
        min_markets_for_diverse: int = 3,
    ) -> None:
        self._new_days = new_wallet_days
        self._min_trades = min_trades_for_established
        self._min_markets = min_markets_for_diverse

    @property
    def name(self) -> str:
        return "account_age"

    async def score(
        self, trade: Trade, context: ScoringContext,
    ) -> ScoreResult:
        trade_count = await context.db.get_wallet_trade_count(
            trade.proxy_wallet,
        )
        first_seen = await context.db.get_wallet_first_seen(
            trade.proxy_wallet,
        )
        unique_markets = await context.db.get_wallet_unique_markets(
            trade.proxy_wallet,
        )

        reasons: list[str] = []
        sub_scores: list[float] = []

        # Age score: newer wallets score higher
        if first_seen is not None:
            age_seconds = trade.timestamp - first_seen
            age_days = age_seconds / 86400
            if age_days < self._new_days:
                age_score = 1.0 - (age_days / self._new_days)
                sub_scores.append(age_score)
                reasons.append(f"Wallet age: {age_days:.1f} days")
            else:
                sub_scores.append(0.0)
        else:
            # Brand new wallet — first trade we've ever seen
            sub_scores.append(1.0)
            reasons.append("Brand new wallet (first trade)")

        # Activity score: low trade count
        if trade_count < self._min_trades:
            activity_score = 1.0 - (
                trade_count / self._min_trades
            )
            sub_scores.append(activity_score)
            reasons.append(f"Low activity: {trade_count} trades")
        else:
            sub_scores.append(0.0)

        # Diversity score: single-market wallets are suspicious
        if unique_markets < self._min_markets:
            diversity_score = 1.0 - (
                unique_markets / self._min_markets
            )
            sub_scores.append(diversity_score)
            reasons.append(
                f"Low diversity: {unique_markets} market(s)",
            )
        else:
            sub_scores.append(0.0)

        # Average the sub-scores
        final = sum(sub_scores) / len(sub_scores) if sub_scores else 0.0

        return ScoreResult(
            scorer_name=self.name,
            score=min(final, 1.0),
            reason="; ".join(reasons) if reasons and final > 0 else "",
        )
