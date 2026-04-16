"""Trade size scorer — flags trades with unusually large USDC value."""

from __future__ import annotations

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


class TradeSizeScorer:
    """Detects whale trades by absolute size and statistical deviation.

    Two complementary methods:
    1. Absolute: any trade above X USDC scores 1.0
    2. Z-score: how many stddevs above the market's rolling average
    """

    def __init__(
        self,
        absolute_threshold: float = 10_000.0,
        z_score_threshold: float = 3.0,
        rolling_window: int = 500,
    ) -> None:
        self._absolute = absolute_threshold
        self._z_threshold = z_score_threshold
        self._window = rolling_window

    @property
    def name(self) -> str:
        return "trade_size"

    async def score(self, trade: Trade, context: ScoringContext) -> ScoreResult:
        reasons: list[str] = []

        # Method 1: absolute threshold
        absolute_score = 0.0
        if trade.usdc_value >= self._absolute:
            absolute_score = 1.0
            reasons.append(
                f"Trade size ${trade.usdc_value:,.0f} exceeds "
                f"${self._absolute:,.0f} threshold"
            )

        # Method 2: z-score against rolling stats
        z_score_normalized = 0.0
        stats = await context.db.get_rolling_stats(
            trade.condition_id, self._window
        )
        if stats and stats.stddev > 0:
            z = (trade.usdc_value - stats.mean) / stats.stddev
            if z > 0:
                z_score_normalized = min(z / self._z_threshold, 1.0)
                if z >= self._z_threshold:
                    reasons.append(
                        f"Trade is {z:.1f} stddevs above market average "
                        f"(${stats.mean:,.0f} avg, ${stats.stddev:,.0f} stddev)"
                    )

        final_score = max(absolute_score, z_score_normalized)

        return ScoreResult(
            scorer_name=self.name,
            score=min(final_score, 1.0),
            reason="; ".join(reasons) if reasons else "",
        )
