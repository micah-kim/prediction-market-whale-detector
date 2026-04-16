"""Telegram bot alert sink."""

from __future__ import annotations

import logging

import httpx

from whale_detector.models import Alert, ImpactLevel

logger = logging.getLogger(__name__)

_IMPACT_LABEL = {
    ImpactLevel.HIGH: "HIGH",
    ImpactLevel.MEDIUM: "MEDIUM",
    ImpactLevel.LOW: "LOW",
}

_TELEGRAM_API = "https://api.telegram.org"


def _truncate_wallet(address: str) -> str:
    if len(address) > 12:
        return f"{address[:6]}...{address[-4:]}"
    return address


class TelegramBotSink:
    """Sends alerts to a Telegram chat via the Bot API."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(self, alert: Alert) -> None:
        trade = alert.trade
        impact = alert.impact

        reasons_text = ""
        if alert.reasons:
            reasons_text = "\n".join(f"  - {r}" for r in alert.reasons)
            reasons_text = f"\n<b>Reasons:</b>\n{reasons_text}"

        text = (
            f"<b>Whale Alert — {_IMPACT_LABEL[impact]}</b>\n\n"
            f"<b>Market:</b> {_escape_html(trade.title)}\n"
            f"<b>Outcome:</b> {_escape_html(trade.outcome)} ({trade.side})\n"
            f"<b>Size:</b> ${trade.usdc_value:,.2f} "
            f"({trade.size:,.0f} shares @ ${trade.price:.3f})\n"
            f"<b>Wallet:</b> <code>{_truncate_wallet(trade.proxy_wallet)}</code> "
            f"({_escape_html(trade.pseudonym or 'anon')})\n"
            f"<b>Score:</b> {alert.composite_score:.2f}\n"
            f"<b>Time:</b> {trade.trade_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
            f"{reasons_text}"
        )

        url = f"{_TELEGRAM_API}/bot{self._bot_token}/sendMessage"
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        try:
            resp = await self._client.post(url, json=payload)
            data = resp.json()
            if not data.get("ok"):
                logger.warning(
                    "Telegram API error: %s",
                    data.get("description", resp.text[:200]),
                )
        except httpx.HTTPError as exc:
            logger.error("Telegram send failed: %s", exc)


def _escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
