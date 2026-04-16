"""Timing scorer — flags trades placed close to market resolution."""

from __future__ import annotations

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


class TimingScorer:
    """Detects suspiciously timed trades near market resolution.

    Higher score when a trade is placed within a configurable window
    of the market's end date, especially on a minority outcome
    (suggesting foreknowledge of an unlikely result).
    """

    def __init__(
        self,
        window_hours: float = 24.0,
        minority_price_threshold: float = 0.35,
    ) -> None:
        self._window_hours = window_hours
        self._minority_threshold = minority_price_threshold

    @property
    def name(self) -> str:
        return "timing"

    async def score(
        self, trade: Trade, context: ScoringContext,
    ) -> ScoreResult:
        if not context.gamma_api:
            return ScoreResult(scorer_name=self.name, score=0.0)

        market = await context.gamma_api.get_market_by_condition(
            trade.condition_id,
        )
        if not market or not market.end_date:
            return ScoreResult(scorer_name=self.name, score=0.0)

        trade_dt = trade.trade_time
        hours_to_end = (
            market.end_date - trade_dt
        ).total_seconds() / 3600

        if hours_to_end <= 0 or hours_to_end > self._window_hours:
            return ScoreResult(scorer_name=self.name, score=0.0)

        # Proximity score: closer to resolution = higher score
        proximity = max(0.0, 1.0 - hours_to_end / self._window_hours)

        # Minority boost: betting on an unlikely outcome amplifies
        minority_mult = 1.0
        if trade.price < self._minority_threshold:
            minority_mult = 1.5

        raw_score = min(proximity * minority_mult, 1.0)

        reason = ""
        if raw_score > 0:
            reason = (
                f"Trade placed {hours_to_end:.1f}h before resolution"
            )
            if trade.price < self._minority_threshold:
                reason += (
                    f" on minority outcome "
                    f"(price ${trade.price:.3f})"
                )

        return ScoreResult(
            scorer_name=self.name,
            score=raw_score,
            reason=reason,
        )
