"""Data models for trades, alerts, and scoring."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, computed_field


class ImpactLevel(StrEnum):
    """Alert impact classification inspired by Polywhaler's trade impact scoring."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Trade(BaseModel):
    """Normalized trade from the Polymarket Data API.

    Raw API fields are mapped to snake_case. The `usdc_value` is computed
    from `size * price` since raw share count is meaningless without price.
    """

    proxy_wallet: str
    side: str  # "BUY" or "SELL"
    asset: str  # token ID
    condition_id: str
    size: float
    price: float
    timestamp: int  # unix epoch
    title: str
    slug: str
    event_slug: str = ""
    outcome: str  # "Yes" or "No"
    outcome_index: int
    pseudonym: str = ""
    transaction_hash: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usdc_value(self) -> float:
        """Dollar value of the trade: shares * price per share."""
        return self.size * self.price

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trade_time(self) -> datetime:
        """Trade timestamp as a timezone-aware datetime."""
        return datetime.fromtimestamp(self.timestamp, tz=UTC)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Trade:
        """Create a Trade from a raw Data API response dict."""
        return cls(
            proxy_wallet=data["proxyWallet"],
            side=data["side"],
            asset=data.get("asset", ""),
            condition_id=data.get("conditionId", ""),
            size=float(data["size"]),
            price=float(data["price"]),
            timestamp=int(data["timestamp"]),
            title=data.get("title", ""),
            slug=data.get("slug", ""),
            event_slug=data.get("eventSlug", ""),
            outcome=data.get("outcome", ""),
            outcome_index=int(data.get("outcomeIndex", 0)),
            pseudonym=data.get("pseudonym", data.get("name", "")),
            transaction_hash=data.get("transactionHash", ""),
        )


class RollingStats(BaseModel):
    """Rolling statistics for a market's trade sizes."""

    mean: float
    stddev: float
    count: int


class ScoreResult(BaseModel):
    """Result from a single scorer."""

    scorer_name: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class Alert(BaseModel):
    """An alert generated when a trade exceeds the anomaly threshold."""

    trade: Trade
    scores: list[ScoreResult]
    composite_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def impact(self) -> ImpactLevel:
        """Classify alert impact based on composite score thresholds."""
        if self.composite_score >= 0.8:
            return ImpactLevel.HIGH
        if self.composite_score >= 0.5:
            return ImpactLevel.MEDIUM
        return ImpactLevel.LOW

    @computed_field  # type: ignore[prop-decorator]
    @property
    def reasons(self) -> list[str]:
        """Human-readable list of reasons from individual scorers."""
        return [s.reason for s in self.scores if s.reason and s.score > 0]


class MarketDetail(BaseModel):
    """Market metadata from the Gamma API."""

    condition_id: str
    slug: str
    question: str = ""
    end_date: datetime | None = None
    active: bool = True
    closed: bool = False
    volume: float = 0.0
    liquidity: float = 0.0
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float] = Field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> MarketDetail:
        end_date = None
        if data.get("endDate"):
            with contextlib.suppress(ValueError, AttributeError):
                end_date = datetime.fromisoformat(
                    data["endDate"].replace("Z", "+00:00")
                )

        outcome_prices: list[float] = []
        if data.get("outcomePrices"):
            try:
                raw = data["outcomePrices"]
                if isinstance(raw, str):
                    import json
                    raw = json.loads(raw)
                outcome_prices = [float(p) for p in raw]
            except (ValueError, TypeError):
                pass

        outcomes: list[str] = []
        if data.get("outcomes"):
            try:
                raw_outcomes = data["outcomes"]
                if isinstance(raw_outcomes, str):
                    import json
                    raw_outcomes = json.loads(raw_outcomes)
                outcomes = [str(o) for o in raw_outcomes]
            except (ValueError, TypeError):
                pass

        return cls(
            condition_id=data.get("conditionId", ""),
            slug=data.get("slug", ""),
            question=data.get("question", ""),
            end_date=end_date,
            active=bool(data.get("active", True)),
            closed=bool(data.get("closed", False)),
            volume=float(data.get("volume", 0)),
            liquidity=float(data.get("liquidity", 0)),
            outcomes=outcomes,
            outcome_prices=outcome_prices,
        )


class WalletProfile(BaseModel):
    """Aggregated profile of a wallet's trading activity."""

    address: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    total_trades: int = 0
    unique_markets: int = 0
    total_usdc_volume: float = 0.0
    buy_count: int = 0
    sell_count: int = 0
    pseudonym: str = ""


class CoordinatedEntry(BaseModel):
    """A detected burst of coordinated minority-side entries in a market."""

    condition_id: str
    market_title: str = ""
    market_slug: str = ""
    outcome: str = ""
    avg_price: float = 0.0
    wallets: list[str] = Field(default_factory=list)
    fresh_wallet_count: int = 0
    total_usdc: float = 0.0
    time_spread_seconds: float = 0.0
    first_entry: int = 0  # timestamp
    last_entry: int = 0  # timestamp
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    trade_count: int = 0
