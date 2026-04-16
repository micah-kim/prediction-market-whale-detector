"""Stats endpoints — overview numbers, top markets, top wallets."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.db import Database

router = APIRouter(tags=["stats"])


@router.get("/stats")
async def global_stats(db: Database = Depends(get_db)) -> dict:
    stats = await db.get_global_stats()
    stats["alert_count"] = await db.get_alert_count()
    return stats


@router.get("/stats/top-markets")
async def top_markets(
    limit: int = 10,
    db: Database = Depends(get_db),
) -> list[dict]:
    return await db.get_top_markets(limit)


@router.get("/stats/top-wallets")
async def top_wallets(
    limit: int = 10,
    db: Database = Depends(get_db),
) -> list[dict]:
    return await db.get_top_wallets(limit)
