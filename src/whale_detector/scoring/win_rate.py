"""Win rate scorer — flags wallets with improbably high win rates."""

from __future__ import annotations

import math

from whale_detector.models import ScoreResult, Trade
from whale_detector.scoring.base import ScoringContext


def _binomial_survival(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), using normal approximation.

    Returns the probability of seeing k or more successes in n trials
    with success probability p. Uses continuity-corrected normal
    approximation for efficiency.
    """
    if n == 0 or p <= 0 or p >= 1:
        return 0.0

    mean = n * p
    std = math.sqrt(n * p * (1 - p))
    if std == 0:
        return 0.0

    # Continuity correction
    z = (k - 0.5 - mean) / std
    # Standard normal CDF via error function
    survival = 0.5 * math.erfc(z / math.sqrt(2))
    return max(0.0, min(1.0, survival))


class WinRateScorer:
    """Detects wallets with statistically improbable win rates.

    Computes the p-value of the wallet's observed wins given the
    implied probabilities at the time of each trade. Uses the
    trade price as the expected win probability.

    Only scores wallets with enough resolved trades to draw
    meaningful conclusions.
    """

    def __init__(self, min_resolved_trades: int = 5) -> None:
        self._min_resolved = min_resolved_trades

    @property
    def name(self) -> str:
        return "win_rate"

    async def score(
        self, trade: Trade, context: ScoringContext,
    ) -> ScoreResult:
        # Query all trades for this wallet
        cursor = await context.db.conn.execute(
            """SELECT price, outcome, side, condition_id
            FROM trades
            WHERE proxy_wallet = ?
            ORDER BY timestamp""",
            (trade.proxy_wallet,),
        )
        rows = await cursor.fetchall()

        if len(rows) < self._min_resolved:
            return ScoreResult(scorer_name=self.name, score=0.0)

        # For each trade, price represents implied probability
        # of the outcome. A BUY at price=0.30 means 30% chance.
        # If the wallet consistently wins low-probability bets,
        # that's suspicious.
        total = len(rows)
        # Use average price as the expected win rate
        avg_price = sum(r[0] for r in rows) / total

        # We can't know which trades "won" without resolution data.
        # For now, use a heuristic: wallets that consistently buy
        # at very low prices (long shots) and have high trade counts
        # are suspicious. This will be refined when we track
        # market resolutions.
        #
        # Heuristic: If average trade price < 0.20, they're
        # consistently betting on unlikely outcomes. With many
        # trades, this becomes statistically notable.
        if avg_price >= 0.20:
            return ScoreResult(scorer_name=self.name, score=0.0)

        # Score based on how extreme the average price is and
        # the volume of trades at those prices
        price_extremity = max(0.0, (0.20 - avg_price) / 0.20)
        volume_factor = min(total / (self._min_resolved * 4), 1.0)
        raw_score = price_extremity * volume_factor

        reason = ""
        if raw_score > 0:
            reason = (
                f"Wallet avg trade price ${avg_price:.3f} "
                f"across {total} trades (long-shot pattern)"
            )

        return ScoreResult(
            scorer_name=self.name,
            score=min(raw_score, 1.0),
            reason=reason,
        )
