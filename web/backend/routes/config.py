"""Config endpoint — read-only view of effective configuration."""

from __future__ import annotations

from fastapi import APIRouter

from whale_detector.config import load_settings

router = APIRouter(tags=["config"])


@router.get("/config")
async def effective_config() -> dict:
    settings = load_settings()
    return settings.model_dump()
