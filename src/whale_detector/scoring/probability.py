"""Probability scorer — flags large bets on low-probability outcomes."""

from __future__ import annotations

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


class ProbabilityScorer:
    """Detects large trades on extreme-probability outcomes.

    Inspired by Polywhaler's "low probability bets" signal. Most traders
    avoid placing large bets on outcomes priced below ~$0.15 (15% chance).
    When someone does, it may indicate insider knowledge.

    The score increases with both the extremity of the price and the
    size of the trade.
    """

    def __init__(
        self,
        low_prob_threshold: float = 0.15,
        size_amplifier_usd: float = 1000.0,
    ) -> None:
        self._low_prob = low_prob_threshold
        self._size_amp = size_amplifier_usd

    @property
    def name(self) -> str:
        return "probability"

    async def score(
        self, trade: Trade, context: ScoringContext,
    ) -> ScoreResult:
        # Only flag BUY trades on low-probability outcomes.
        # SELL at low prices is just exiting a position.
        if trade.side != "BUY":
            return ScoreResult(scorer_name=self.name, score=0.0)

        if trade.price >= self._low_prob:
            return ScoreResult(scorer_name=self.name, score=0.0)

        # Price extremity: lower price = higher score
        # At price=0.01, extremity=0.93; at price=0.10, extremity=0.33
        price_score = (self._low_prob - trade.price) / self._low_prob

        # Size amplifier: larger trades at low prices are more notable
        size_factor = min(trade.usdc_value / self._size_amp, 1.0)

        # Combine: both price extremity and size matter
        raw_score = price_score * (0.5 + 0.5 * size_factor)

        reason = ""
        if raw_score > 0:
            pct = trade.price * 100
            reason = (
                f"${trade.usdc_value:,.0f} BUY at "
                f"{pct:.1f}% probability "
                f"({trade.size:,.0f} shares @ ${trade.price:.3f})"
            )

        return ScoreResult(
            scorer_name=self.name,
            score=min(raw_score, 1.0),
            reason=reason,
        )
