"""Shared test fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from whale_detector.models import Trade


def make_trade_data(**overrides: Any) -> dict[str, Any]:
    """Create a raw Data API trade dict with sensible defaults."""
    base = {
        "proxyWallet": "0xabc123def456abc123def456abc123def456abc1",
        "side": "BUY",
        "asset": "token123",
        "conditionId": "0xcondition123",
        "size": 100.0,
        "price": 0.65,
        "timestamp": 1700000000,
        "title": "Will X happen?",
        "slug": "will-x-happen",
        "eventSlug": "x-event",
        "outcome": "Yes",
        "outcomeIndex": 0,
        "pseudonym": "TestWhale",
        "name": "TestWhale",
        "transactionHash": "0xtxhash123",
    }
    base.update(overrides)
    return base


@pytest.fixture
def sample_trade_data() -> dict[str, Any]:
    return make_trade_data()


@pytest.fixture
def sample_trade() -> Trade:
    return Trade.from_api(make_trade_data())


@pytest.fixture
def whale_trade() -> Trade:
    """A large trade that should trigger absolute threshold alerts."""
    return Trade.from_api(
        make_trade_data(
            size=20000.0,
            price=0.90,
            transactionHash="0xwhale_tx",
            pseudonym="BigFish",
        )
    )
