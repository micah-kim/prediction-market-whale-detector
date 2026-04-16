"""Scorer protocol and composite scoring system."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from whale_detector.db import Database
from whale_detector.models import Alert, CoordinatedEntry, ScoreResult, Trade

if TYPE_CHECKING:
    from whale_detector.api.gamma_api import GammaAPI


class ScoringContext:
    """Shared context passed to all scorers during evaluation."""

    def __init__(
        self,
        db: Database,
        gamma_api: GammaAPI | None = None,
    ) -> None:
        self.db = db
        self.gamma_api = gamma_api
        self.coordinated_entries: list[CoordinatedEntry] = []


@runtime_checkable
class Scorer(Protocol):
    """Protocol for individual anomaly detection scorers.

    Each scorer evaluates a single trade and returns a ScoreResult
    with a value in [0.0, 1.0] and a human-readable explanation.
    """

    @property
    def name(self) -> str: ...

    async def score(self, trade: Trade, context: ScoringContext) -> ScoreResult: ...


class CompositeScorer:
    """Aggregates multiple scorers with configurable weights.

    The composite score is a weighted average normalized to [0, 1].
    """

    def __init__(self, scorers: list[tuple[Scorer, float]]) -> None:
        self._scorers = scorers
        total = sum(w for _, w in scorers)
        self._total_weight = total if total > 0 else 1.0

    async def evaluate(
        self, trade: Trade, context: ScoringContext, threshold: float = 0.5
    ) -> Alert | None:
        """Score a trade through all scorers. Returns an Alert if above threshold."""
        results: list[ScoreResult] = []
        weighted_sum = 0.0

        for scorer, weight in self._scorers:
            result = await scorer.score(trade, context)
            results.append(result)
            weighted_sum += result.score * weight

        composite = weighted_sum / self._total_weight

        if composite < threshold:
            return None

        return Alert(
            trade=trade,
            scores=results,
            composite_score=composite,
        )
