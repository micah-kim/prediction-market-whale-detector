"""FastAPI application — read-only web API for the whale detector dashboard."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from web.backend.deps import set_db, set_gamma_api
from web.backend.routes import (
    alerts,
    config,
    coordination,
    markets,
    paper,
    stats,
    trades,
    wallets,
)
from whale_detector.api.client import PolymarketClient
from whale_detector.api.gamma_api import GammaAPI
from whale_detector.config import load_settings
from whale_detector.db import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    db = Database(settings.resolved_db_path)
    await db.initialize()
    await db.initialize_paper_trading(
        settings.paper_trading.initial_bankroll,
    )
    set_db(db)

    client = PolymarketClient()
    await client.__aenter__()
    gamma_api = GammaAPI(client, cache_ttl=30)
    set_gamma_api(gamma_api)

    yield

    await client.__aexit__(None, None, None)
    await db.close()


app = FastAPI(
    title="Whale Detector API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stats.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(markets.router, prefix="/api")
app.include_router(wallets.router, prefix="/api")
app.include_router(coordination.router, prefix="/api")
app.include_router(config.router, prefix="/api")
app.include_router(paper.router, prefix="/api")
