"""Discord webhook alert sink."""

from __future__ import annotations

import logging

import httpx

from whale_detector.models import Alert, ImpactLevel

logger = logging.getLogger(__name__)

_IMPACT_COLORS = {
    ImpactLevel.HIGH: 0xFF0000,    # red
    ImpactLevel.MEDIUM: 0xFFAA00,  # orange
    ImpactLevel.LOW: 0x3498DB,     # blue
}


def _truncate_wallet(address: str) -> str:
    if len(address) > 12:
        return f"{address[:6]}...{address[-4:]}"
    return address


class DiscordWebhookSink:
    """Sends alerts to a Discord channel via webhook."""

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url
        self._client = httpx.AsyncClient(timeout=10.0)

    async def send(self, alert: Alert) -> None:
        trade = alert.trade
        impact = alert.impact

        fields = [
            {
                "name": "Market",
                "value": trade.title or "N/A",
                "inline": False,
            },
            {
                "name": "Outcome",
                "value": f"{trade.outcome} ({trade.side})",
                "inline": True,
            },
            {
                "name": "Size",
                "value": (
                    f"${trade.usdc_value:,.2f} "
                    f"({trade.size:,.0f} shares @ ${trade.price:.3f})"
                ),
                "inline": True,
            },
            {
                "name": "Wallet",
                "value": (
                    f"`{_truncate_wallet(trade.proxy_wallet)}` "
                    f"({trade.pseudonym or 'anon'})"
                ),
                "inline": True,
            },
            {"name": "Score", "value": f"{alert.composite_score:.2f}", "inline": True},
            {"name": "Impact", "value": impact.value.upper(), "inline": True},
            {
                "name": "Time",
                "value": trade.trade_time.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "inline": True,
            },
        ]

        if alert.reasons:
            fields.append({
                "name": "Reasons",
                "value": "\n".join(f"- {r}" for r in alert.reasons),
                "inline": False,
            })

        embed = {
            "title": "Whale Alert",
            "color": _IMPACT_COLORS.get(impact, 0x3498DB),
            "fields": fields,
        }

        payload = {"embeds": [embed]}

        try:
            resp = await self._client.post(self._url, json=payload)
            if resp.status_code not in (200, 204):
                logger.warning(
                    "Discord webhook returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
        except httpx.HTTPError as exc:
            logger.error("Discord webhook failed: %s", exc)
