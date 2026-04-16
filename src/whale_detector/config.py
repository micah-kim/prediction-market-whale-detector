"""Configuration loading with three-layer precedence: CLI > env vars > TOML file."""

from __future__ import annotations

import os
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_CONFIG_SEARCH_PATHS = [
    Path("config.toml"),
    Path.home() / ".config" / "whale-detector" / "config.toml",
]


class ThresholdSettings(BaseModel):
    absolute_size_usd: float = 10_000.0
    z_score_threshold: float = 3.0
    rolling_window_trades: int = 500
    alert_threshold: float = 0.5
    timing_window_hours: float = 24.0
    minority_price_threshold: float = 0.35
    new_wallet_days: float = 7.0
    min_trades_established: int = 10
    min_markets_diverse: int = 3
    win_rate_min_trades: int = 5
    low_prob_threshold: float = 0.15
    prob_size_amplifier: float = 1000.0
    coordination_lookback_seconds: int = 3600
    coordination_min_wallets: int = 3
    coordination_max_price: float = 0.20
    coordination_fresh_threshold: int = 5
    coordination_tight_window: int = 1800
    coordination_min_confidence: float = 0.4


class ScoringWeights(BaseModel):
    trade_size_weight: float = 0.25
    timing_weight: float = 0.15
    account_age_weight: float = 0.15
    win_rate_weight: float = 0.10
    probability_weight: float = 0.15
    coordination_weight: float = 0.20


class AlertingSettings(BaseModel):
    sinks: list[str] = Field(default_factory=lambda: ["terminal"])
    discord_webhook_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""


class MarketFilter(BaseModel):
    watch_slugs: list[str] = Field(default_factory=list)
    exclude_slug_patterns: list[str] = Field(
        default_factory=lambda: [
            "btc-above-*",
            "btc-below-*",
            "eth-above-*",
            "eth-below-*",
            "btc-updown-*",
            "eth-updown-*",
            "bitcoin-above-*",
            "bitcoin-below-*",
            "bitcoin-up-or-down-*",
            "ethereum-above-*",
            "ethereum-below-*",
            "ethereum-up-or-down-*",
            "highest-temperature-*",
        ]
    )

    def is_excluded(self, slug: str) -> bool:
        """Check if a market slug matches any exclusion pattern."""
        return any(fnmatch(slug, pattern) for pattern in self.exclude_slug_patterns)

    def is_watched(self, slug: str) -> bool:
        """Check if a market slug passes the filter.

        If watch_slugs is non-empty, only those slugs pass.
        Otherwise, anything not excluded passes.
        """
        if self.watch_slugs:
            return slug in self.watch_slugs
        return not self.is_excluded(slug)


class PaperTradingSettings(BaseModel):
    enabled: bool = False
    initial_bankroll: float = 10_000.0
    risk_per_trade_pct: float = 0.02
    min_alert_score: float = 0.5
    resolution_poll_interval: int = 3600


class Settings(BaseModel):
    db_path: str = "~/.local/share/whale-detector/trades.db"
    poll_interval_seconds: int = 5
    log_level: str = "INFO"
    thresholds: ThresholdSettings = Field(default_factory=ThresholdSettings)
    scoring: ScoringWeights = Field(default_factory=ScoringWeights)
    alerting: AlertingSettings = Field(default_factory=AlertingSettings)
    markets: MarketFilter = Field(default_factory=MarketFilter)
    paper_trading: PaperTradingSettings = Field(
        default_factory=PaperTradingSettings,
    )

    @property
    def resolved_db_path(self) -> Path:
        """Expand ~ and return an absolute Path for the database file."""
        return Path(self.db_path).expanduser()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_toml(path: Path | None) -> dict[str, Any]:
    """Load a TOML config file, returning empty dict if not found."""
    if path is not None:
        p = Path(path).expanduser()
        if p.exists():
            with open(p, "rb") as f:
                return tomllib.load(f)
        return {}

    for candidate in _CONFIG_SEARCH_PATHS:
        candidate = candidate.expanduser()
        if candidate.exists():
            with open(candidate, "rb") as f:
                return tomllib.load(f)
    return {}


def _load_env_overrides() -> dict[str, Any]:
    """Load settings from WHALE_DETECTOR_* environment variables.

    Supports flat keys like WHALE_DETECTOR_POLL_INTERVAL_SECONDS=10
    and nested keys like WHALE_DETECTOR_THRESHOLDS__ABSOLUTE_SIZE_USD=5000.
    """
    prefix = "WHALE_DETECTOR_"
    overrides: dict[str, Any] = {}

    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        parts = key[len(prefix) :].lower().split("__")
        target = overrides
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        # Try to parse as number
        try:
            target[parts[-1]] = int(value)
        except ValueError:
            try:
                target[parts[-1]] = float(value)
            except ValueError:
                target[parts[-1]] = value

    return overrides


def load_settings(
    config_path: str | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> Settings:
    """Load settings with three-layer precedence: CLI > env > TOML > defaults."""
    toml_data = _load_toml(Path(config_path) if config_path else None)

    # Flatten [general] section to top level
    general = toml_data.pop("general", {})
    merged = _deep_merge(general, toml_data)

    env_data = _load_env_overrides()
    merged = _deep_merge(merged, env_data)

    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    return Settings(**merged)
