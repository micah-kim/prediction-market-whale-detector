"""FastAPI dependencies — shared Database and API instances."""

from __future__ import annotations

from whale_detector.api.gamma_api import GammaAPI
from whale_detector.db import Database

_db: Database | None = None
_gamma_api: GammaAPI | None = None


def get_db() -> Database:
    """Return the shared Database instance."""
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


def set_db(db: Database) -> None:
    """Set the shared Database instance (called during lifespan)."""
    global _db
    _db = db


def get_gamma_api() -> GammaAPI | None:
    """Return the shared GammaAPI instance (may be None)."""
    return _gamma_api


def set_gamma_api(api: GammaAPI) -> None:
    """Set the shared GammaAPI instance (called during lifespan)."""
    global _gamma_api
    _gamma_api = api
