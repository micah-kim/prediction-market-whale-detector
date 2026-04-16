"""Coordination endpoints — coordinated entry patterns."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.config import load_settings
from whale_detector.coordination import CoordinatedEntryDetector
from whale_detector.db import Database

router = APIRouter(tags=["coordination"])


@router.get("/coordination")
async def coordination_patterns(
    lookback: int | None = None,
    min_wallets: int | None = None,
    max_price: float | None = None,
    min_confidence: float | None = None,
    db: Database = Depends(get_db),
) -> list[dict]:
    settings = load_settings()
    t = settings.thresholds

    detector = CoordinatedEntryDetector(
        lookback_seconds=lookback or t.coordination_lookback_seconds,
        min_wallets=min_wallets or t.coordination_min_wallets,
        max_price=max_price or t.coordination_max_price,
        min_confidence=min_confidence or t.coordination_min_confidence,
    )
    entries = await detector.scan(db)
    return [e.model_dump() for e in entries]
