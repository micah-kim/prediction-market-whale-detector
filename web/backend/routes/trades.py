"""Trades endpoints — recent trades feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.db import Database

router = APIRouter(tags=["trades"])


@router.get("/trades/live")
async def live_trades(
    limit: int = 30,
    db: Database = Depends(get_db),
) -> list[dict]:
    trades = await db.get_recent_trades_all(limit)
    return [t.model_dump() for t in trades]
