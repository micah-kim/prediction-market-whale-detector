"""Tests for webhook alert sinks (Discord and Telegram)."""

from __future__ import annotations

import pytest
import respx
import httpx

from whale_detector.alerting.discord import DiscordWebhookSink
from whale_detector.alerting.telegram import TelegramBotSink, _escape_html
from whale_detector.models import Alert, ScoreResult, Trade

from conftest import make_trade_data


def _make_alert(score: float = 0.85) -> Alert:
    trade = Trade.from_api(make_trade_data(
        size=20000.0,
        price=0.90,
        pseudonym="TestWhale",
        title="Will X happen?",
    ))
    return Alert(
        trade=trade,
        scores=[
            ScoreResult(
                scorer_name="trade_size", score=1.0,
                reason="$18K exceeds $10K threshold",
            ),
        ],
        composite_score=score,
    )


class TestDiscordWebhookSink:
    @respx.mock
    async def test_sends_embed(self) -> None:
        url = "https://discord.com/api/webhooks/123/abc"
        route = respx.post(url).mock(
            return_value=httpx.Response(204)
        )

        sink = DiscordWebhookSink(url)
        await sink.send(_make_alert())

        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "Whale Alert" in body
        assert "TestWhale" in body

    @respx.mock
    async def test_handles_error_status(self) -> None:
        url = "https://discord.com/api/webhooks/123/abc"
        respx.post(url).mock(
            return_value=httpx.Response(429, text="rate limited")
        )

        sink = DiscordWebhookSink(url)
        # Should not raise
        await sink.send(_make_alert())

    @respx.mock
    async def test_handles_network_error(self) -> None:
        url = "https://discord.com/api/webhooks/123/abc"
        respx.post(url).mock(side_effect=httpx.ConnectError("timeout"))

        sink = DiscordWebhookSink(url)
        # Should not raise
        await sink.send(_make_alert())


class TestTelegramBotSink:
    @respx.mock
    async def test_sends_message(self) -> None:
        token = "123:ABC"
        chat_id = "-100999"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        route = respx.post(url).mock(
            return_value=httpx.Response(200, json={"ok": True})
        )

        sink = TelegramBotSink(token, chat_id)
        await sink.send(_make_alert())

        assert route.called
        request = route.calls[0].request
        body = request.content.decode()
        assert "Whale Alert" in body
        assert chat_id in body

    @respx.mock
    async def test_handles_api_error(self) -> None:
        token = "123:ABC"
        chat_id = "-100999"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        respx.post(url).mock(
            return_value=httpx.Response(
                200, json={"ok": False, "description": "bad request"},
            )
        )

        sink = TelegramBotSink(token, chat_id)
        # Should not raise
        await sink.send(_make_alert())

    @respx.mock
    async def test_handles_network_error(self) -> None:
        token = "123:ABC"
        chat_id = "-100999"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        respx.post(url).mock(side_effect=httpx.ConnectError("timeout"))

        sink = TelegramBotSink(token, chat_id)
        # Should not raise
        await sink.send(_make_alert())


class TestEscapeHtml:
    def test_escapes_special_chars(self) -> None:
        assert _escape_html("<b>foo</b>") == "&lt;b&gt;foo&lt;/b&gt;"

    def test_escapes_ampersand(self) -> None:
        assert _escape_html("A & B") == "A &amp; B"

    def test_no_change_for_safe_text(self) -> None:
        assert _escape_html("hello world") == "hello world"
