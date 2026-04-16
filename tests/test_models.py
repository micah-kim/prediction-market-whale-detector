"""Tests for data models."""

from __future__ import annotations

from whale_detector.models import Alert, ImpactLevel, ScoreResult, Trade

from conftest import make_trade_data


class TestTrade:
    def test_from_api(self, sample_trade_data: dict) -> None:
        trade = Trade.from_api(sample_trade_data)
        assert trade.proxy_wallet == "0xabc123def456abc123def456abc123def456abc1"
        assert trade.side == "BUY"
        assert trade.size == 100.0
        assert trade.price == 0.65
        assert trade.outcome == "Yes"
        assert trade.pseudonym == "TestWhale"
        assert trade.transaction_hash == "0xtxhash123"

    def test_usdc_value(self, sample_trade: Trade) -> None:
        assert sample_trade.usdc_value == pytest.approx(65.0)

    def test_usdc_value_large(self, whale_trade: Trade) -> None:
        assert whale_trade.usdc_value == pytest.approx(18000.0)

    def test_trade_time(self, sample_trade: Trade) -> None:
        assert sample_trade.trade_time.year == 2023
        assert sample_trade.trade_time.tzname() == "UTC"

    def test_from_api_missing_optional_fields(self) -> None:
        data = {
            "proxyWallet": "0xwallet",
            "side": "SELL",
            "size": 50.0,
            "price": 0.30,
            "timestamp": 1700000000,
            "transactionHash": "0xtx",
        }
        trade = Trade.from_api(data)
        assert trade.proxy_wallet == "0xwallet"
        assert trade.title == ""
        assert trade.pseudonym == ""


class TestAlert:
    def test_impact_high(self, sample_trade: Trade) -> None:
        alert = Alert(
            trade=sample_trade,
            scores=[ScoreResult(scorer_name="test", score=0.9, reason="big trade")],
            composite_score=0.9,
        )
        assert alert.impact == ImpactLevel.HIGH

    def test_impact_medium(self, sample_trade: Trade) -> None:
        alert = Alert(
            trade=sample_trade,
            scores=[ScoreResult(scorer_name="test", score=0.6, reason="notable trade")],
            composite_score=0.6,
        )
        assert alert.impact == ImpactLevel.MEDIUM

    def test_impact_low(self, sample_trade: Trade) -> None:
        alert = Alert(
            trade=sample_trade,
            scores=[ScoreResult(scorer_name="test", score=0.3, reason="small trade")],
            composite_score=0.3,
        )
        assert alert.impact == ImpactLevel.LOW

    def test_reasons_filters_zero_scores(self, sample_trade: Trade) -> None:
        alert = Alert(
            trade=sample_trade,
            scores=[
                ScoreResult(scorer_name="a", score=0.8, reason="triggered"),
                ScoreResult(scorer_name="b", score=0.0, reason="not triggered"),
            ],
            composite_score=0.5,
        )
        assert alert.reasons == ["triggered"]


import pytest
