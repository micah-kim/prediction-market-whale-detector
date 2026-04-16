"""Markets endpoints — market trades and detail."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.db import Database

router = APIRouter(tags=["markets"])


@router.get("/markets/{slug}")
async def market_trades(
    slug: str,
    limit: int = 50,
    db: Database = Depends(get_db),
) -> list[dict]:
    trades = await db.get_market_trades(slug, limit)
    return [t.model_dump() for t in trades]
