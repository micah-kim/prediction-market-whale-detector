"""Alerts endpoints — alert history and live feed."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.db import Database

router = APIRouter(tags=["alerts"])


@router.get("/alerts")
async def recent_alerts(
    limit: int = 50,
    db: Database = Depends(get_db),
) -> list[dict]:
    return await db.get_recent_alerts(limit)


@router.get("/alerts/live")
async def live_alerts(db: Database = Depends(get_db)) -> list[dict]:
    return await db.get_recent_alerts(10)
