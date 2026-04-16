"""Rich terminal alert output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from whale_detector.models import Alert, ImpactLevel

_IMPACT_COLORS = {
    ImpactLevel.HIGH: "red",
    ImpactLevel.MEDIUM: "yellow",
    ImpactLevel.LOW: "blue",
}

_IMPACT_EMOJI = {
    ImpactLevel.HIGH: "[bold red]HIGH[/]",
    ImpactLevel.MEDIUM: "[bold yellow]MEDIUM[/]",
    ImpactLevel.LOW: "[bold blue]LOW[/]",
}


def _truncate_wallet(address: str) -> str:
    if len(address) > 12:
        return f"{address[:6]}...{address[-4:]}"
    return address


class TerminalAlertSink:
    """Renders alerts as Rich panels in the terminal."""

    def __init__(self) -> None:
        self._console = Console()

    async def send(self, alert: Alert) -> None:
        trade = alert.trade
        impact = alert.impact
        color = _IMPACT_COLORS[impact]

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Market", trade.title)
        table.add_row("Outcome", f"{trade.outcome} ({trade.side})")
        size_str = (
            f"${trade.usdc_value:,.2f} "
            f"({trade.size:,.1f} shares @ ${trade.price:.3f})"
        )
        table.add_row("Size", size_str)
        wallet_str = (
            f"{_truncate_wallet(trade.proxy_wallet)} "
            f"({trade.pseudonym or 'anon'})"
        )
        table.add_row("Wallet", wallet_str)
        table.add_row("Time", trade.trade_time.strftime("%Y-%m-%d %H:%M:%S UTC"))
        table.add_row("Impact", _IMPACT_EMOJI[impact])
        table.add_row("Score", f"{alert.composite_score:.2f}")

        if alert.reasons:
            table.add_row("Reasons", "\n".join(f"  - {r}" for r in alert.reasons))

        panel = Panel(
            table,
            title=f"[bold {color}]Whale Alert[/]",
            border_style=color,
            expand=False,
        )
        self._console.print(panel)
