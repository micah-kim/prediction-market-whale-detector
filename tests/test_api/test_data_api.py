"""Tests for the Data API client."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from whale_detector.api.client import PolymarketClient, DATA_API_BASE
from whale_detector.api.data_api import DataAPI
from whale_detector.config import MarketFilter

from conftest import make_trade_data


@pytest.fixture
def market_filter() -> MarketFilter:
    return MarketFilter()


@pytest.fixture
async def data_api(market_filter: MarketFilter) -> DataAPI:
    client = PolymarketClient()
    yield DataAPI(client, market_filter)
    await client.close()


class TestDataAPI:
    @respx.mock
    async def test_get_recent_trades(self, data_api: DataAPI) -> None:
        mock_response = [
            make_trade_data(transactionHash="0x1"),
            make_trade_data(transactionHash="0x2"),
        ]
        respx.get(f"{DATA_API_BASE}/trades").mock(
            return_value=Response(200, json=mock_response)
        )

        trades = await data_api.get_recent_trades(limit=10)
        assert len(trades) == 2
        assert trades[0].transaction_hash == "0x1"
        assert trades[1].transaction_hash == "0x2"

    @respx.mock
    async def test_filters_excluded_slugs(self) -> None:
        client = PolymarketClient()
        filter_ = MarketFilter(exclude_slug_patterns=["btc-above-*"])
        api = DataAPI(client, filter_)

        mock_response = [
            make_trade_data(slug="btc-above-100k", transactionHash="0x1"),
            make_trade_data(slug="will-x-happen", transactionHash="0x2"),
        ]
        respx.get(f"{DATA_API_BASE}/trades").mock(
            return_value=Response(200, json=mock_response)
        )

        trades = await api.get_recent_trades()
        assert len(trades) == 1
        assert trades[0].slug == "will-x-happen"
        await client.close()

    @respx.mock
    async def test_handles_empty_response(self, data_api: DataAPI) -> None:
        respx.get(f"{DATA_API_BASE}/trades").mock(
            return_value=Response(200, json=[])
        )
        trades = await data_api.get_recent_trades()
        assert trades == []

    @respx.mock
    async def test_handles_malformed_trade(self, data_api: DataAPI) -> None:
        mock_response = [
            {"bad": "data"},  # missing required fields
            make_trade_data(transactionHash="0xgood"),
        ]
        respx.get(f"{DATA_API_BASE}/trades").mock(
            return_value=Response(200, json=mock_response)
        )
        trades = await data_api.get_recent_trades()
        assert len(trades) == 1

    @respx.mock
    async def test_passes_after_timestamp(self, data_api: DataAPI) -> None:
        respx.get(f"{DATA_API_BASE}/trades").mock(
            return_value=Response(200, json=[])
        )
        await data_api.get_recent_trades(after_timestamp=1700000000)
        call = respx.calls.last
        assert call.request.url.params["after"] == "1700000000"
