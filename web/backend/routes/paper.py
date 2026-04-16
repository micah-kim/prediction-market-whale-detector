"""Paper trading endpoints — simulated position tracking."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from web.backend.deps import get_db, get_gamma_api
from whale_detector.config import load_settings
from whale_detector.db import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/paper", tags=["paper-trading"])


@router.get("/summary")
async def paper_summary(db: Database = Depends(get_db)) -> dict:
    return await db.get_paper_summary()


@router.get("/positions")
async def paper_positions(
    status: str | None = None,
    limit: int = 50,
    db: Database = Depends(get_db),
) -> list[dict]:
    return await db.get_paper_trades(status=status, limit=limit)


@router.get("/prices")
async def paper_prices(db: Database = Depends(get_db)) -> dict:
    """Fetch current prices for all open paper trade markets.

    Returns a map of condition_id -> {outcome_name: current_price}.
    Queries Gamma API by slug, falls back to CLOB API by condition_id.
    """
    gamma_api = get_gamma_api()
    if gamma_api is None:
        return {}

    slug_entries = await db.get_open_paper_trade_slugs()
    if not slug_entries:
        return {}

    # Deduplicate slugs (multiple trades may share a slug)
    seen_slugs: dict[str, str] = {}  # slug -> condition_id
    for entry in slug_entries:
        seen_slugs[entry["slug"]] = entry["condition_id"]

    prices: dict[str, dict[str, float]] = {}
    for slug, condition_id in seen_slugs.items():
        try:
            market = await gamma_api.get_market_detail(slug)

            # Fallback to CLOB API for micro-markets not in Gamma
            if not market:
                market = await gamma_api.get_market_from_clob(condition_id)

            if not market:
                continue
            if market.outcomes and market.outcome_prices:
                prices[condition_id] = {}
                for outcome, price in zip(
                    market.outcomes, market.outcome_prices, strict=False,
                ):
                    prices[condition_id][outcome] = price
        except Exception:
            logger.debug("Failed to fetch price for slug %s", slug)

    return prices


@router.post("/reset")
async def reset_paper_trading(db: Database = Depends(get_db)) -> dict:
    settings = load_settings()
    bankroll = settings.paper_trading.initial_bankroll
    await db.reset_paper_trading(bankroll)
    return {"status": "ok", "initial_bankroll": bankroll}
