"""Wallets endpoints — wallet profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from web.backend.deps import get_db
from whale_detector.db import Database

router = APIRouter(tags=["wallets"])


@router.get("/wallets/{address}")
async def wallet_profile(
    address: str,
    db: Database = Depends(get_db),
) -> dict:
    profile = await db.get_wallet_profile(address)
    return profile.model_dump()
