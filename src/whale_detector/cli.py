"""CLI entry point for the whale detector."""

from __future__ import annotations

import asyncio
import logging

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from whale_detector.alerting.terminal import TerminalAlertSink
from whale_detector.api.client import PolymarketClient
from whale_detector.api.data_api import DataAPI
from whale_detector.api.gamma_api import GammaAPI
from whale_detector.config import Settings, load_settings
from whale_detector.coordination import CoordinatedEntryDetector
from whale_detector.db import Database
from whale_detector.monitor import TradeMonitor
from whale_detector.scoring.account_age import AccountAgeScorer
from whale_detector.scoring.base import CompositeScorer
from whale_detector.scoring.coordination import CoordinationScorer
from whale_detector.scoring.probability import ProbabilityScorer
from whale_detector.scoring.timing import TimingScorer
from whale_detector.scoring.trade_size import TradeSizeScorer
from whale_detector.scoring.win_rate import WinRateScorer


@click.group()
@click.version_option(package_name="whale-detector")
def main() -> None:
    """Prediction Market Whale Detector."""


@main.command()
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
@click.option(
    "--threshold", type=float, default=None,
    help="Alert threshold (0.0-1.0)",
)
@click.option(
    "--poll-interval", type=int, default=None,
    help="Seconds between polls",
)
@click.option(
    "--min-size", type=float, default=None,
    help="Minimum USDC trade size to flag",
)
@click.option(
    "--fresh-wallets-only", type=int, default=None,
    help="Only alert on wallets with < N prior trades",
)
@click.option(
    "--log-level", default=None,
    help="Log level (DEBUG, INFO, WARNING, ERROR)",
)
def monitor(
    config_path: str | None,
    threshold: float | None,
    poll_interval: int | None,
    min_size: float | None,
    fresh_wallets_only: int | None,
    log_level: str | None,
) -> None:
    """Start real-time trade monitoring."""
    cli_overrides: dict = {}
    if threshold is not None:
        cli_overrides.setdefault("thresholds", {})[
            "alert_threshold"
        ] = threshold
    if poll_interval is not None:
        cli_overrides["poll_interval_seconds"] = poll_interval
    if min_size is not None:
        cli_overrides.setdefault("thresholds", {})[
            "absolute_size_usd"
        ] = min_size
    if log_level is not None:
        cli_overrides["log_level"] = log_level

    settings = load_settings(
        config_path=config_path,
        cli_overrides=cli_overrides or None,
    )

    logging.basicConfig(
        level=settings.log_level,
        format="%(message)s",
        handlers=[
            RichHandler(rich_tracebacks=True, show_path=False),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    asyncio.run(_run_monitor(settings, fresh_wallets_only))


def _build_scorers(settings: Settings) -> CompositeScorer:
    """Create the composite scorer with all Phase 3 scorers."""
    t = settings.thresholds
    w = settings.scoring
    return CompositeScorer([
        (
            TradeSizeScorer(
                absolute_threshold=t.absolute_size_usd,
                z_score_threshold=t.z_score_threshold,
                rolling_window=t.rolling_window_trades,
            ),
            w.trade_size_weight,
        ),
        (
            TimingScorer(
                window_hours=t.timing_window_hours,
                minority_price_threshold=t.minority_price_threshold,
            ),
            w.timing_weight,
        ),
        (
            AccountAgeScorer(
                new_wallet_days=t.new_wallet_days,
                min_trades_for_established=t.min_trades_established,
                min_markets_for_diverse=t.min_markets_diverse,
            ),
            w.account_age_weight,
        ),
        (
            WinRateScorer(
                min_resolved_trades=t.win_rate_min_trades,
            ),
            w.win_rate_weight,
        ),
        (
            ProbabilityScorer(
                low_prob_threshold=t.low_prob_threshold,
                size_amplifier_usd=t.prob_size_amplifier,
            ),
            w.probability_weight,
        ),
        (
            CoordinationScorer(),
            w.coordination_weight,
        ),
    ])


def _build_sinks(settings: Settings) -> list:
    """Create alert sinks based on config."""
    from whale_detector.alerting.base import AlertSink

    sinks: list[AlertSink] = []

    for sink_name in settings.alerting.sinks:
        if sink_name == "terminal":
            sinks.append(TerminalAlertSink())
        elif sink_name == "discord":
            from whale_detector.alerting.discord import DiscordWebhookSink

            url = settings.alerting.discord_webhook_url
            if not url:
                logging.getLogger(__name__).warning(
                    "Discord sink enabled but discord_webhook_url is empty"
                )
                continue
            sinks.append(DiscordWebhookSink(url))
        elif sink_name == "telegram":
            from whale_detector.alerting.telegram import TelegramBotSink

            token = settings.alerting.telegram_bot_token
            chat_id = settings.alerting.telegram_chat_id
            if not token or not chat_id:
                logging.getLogger(__name__).warning(
                    "Telegram sink enabled but bot_token or chat_id is empty"
                )
                continue
            sinks.append(TelegramBotSink(token, chat_id))

    if not sinks:
        sinks.append(TerminalAlertSink())

    return sinks


async def _run_monitor(
    settings: Settings, fresh_wallets_only: int | None,
) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    t = settings.thresholds
    coord_detector = CoordinatedEntryDetector(
        lookback_seconds=t.coordination_lookback_seconds,
        min_wallets=t.coordination_min_wallets,
        max_price=t.coordination_max_price,
        fresh_threshold=t.coordination_fresh_threshold,
        tight_window_seconds=t.coordination_tight_window,
        min_confidence=t.coordination_min_confidence,
    )

    # Set up paper trader if enabled
    paper_trader = None
    pt = settings.paper_trading
    if pt.enabled:
        from whale_detector.paper_trading import PaperTrader

        await db.initialize_paper_trading(pt.initial_bankroll)
        paper_trader = PaperTrader(
            db=db,
            initial_bankroll=pt.initial_bankroll,
            risk_per_trade_pct=pt.risk_per_trade_pct,
            min_alert_score=pt.min_alert_score,
        )
        logging.getLogger(__name__).info(
            "Paper trading enabled (bankroll: $%.0f, risk: %.0f%%)",
            pt.initial_bankroll,
            pt.risk_per_trade_pct * 100,
        )

    async with PolymarketClient() as client:
        data_api = DataAPI(client, settings.markets)
        gamma_api = GammaAPI(client)
        composite = _build_scorers(settings)
        sinks = _build_sinks(settings)

        # Wire gamma_api into paper trader for resolution checking
        if paper_trader is not None:
            paper_trader._gamma_api = gamma_api

        monitor_inst = TradeMonitor(
            data_api=data_api,
            db=db,
            scorer=composite,
            sinks=sinks,
            settings=settings,
            fresh_wallets_only=fresh_wallets_only,
            gamma_api=gamma_api,
            coordination_detector=coord_detector,
            paper_trader=paper_trader,
            resolution_interval=settings.paper_trading.resolution_poll_interval,
        )

        try:
            await monitor_inst.run()
        finally:
            await db.close()


@main.command()
@click.argument("address")
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
def profile(address: str, config_path: str | None) -> None:
    """Display a wallet's trading profile."""
    settings = load_settings(config_path=config_path)
    asyncio.run(_show_profile(settings, address))


async def _show_profile(settings: Settings, address: str) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    try:
        wp = await db.get_wallet_profile(address)
    finally:
        await db.close()

    console = Console()

    if wp.total_trades == 0:
        console.print(
            f"[yellow]No trades found for {address}[/]",
        )
        return

    table = Table(
        title=f"Wallet Profile: {address}",
        show_header=False,
        box=None,
        padding=(0, 2),
    )
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Pseudonym", wp.pseudonym or "(anonymous)")
    table.add_row("Total Trades", str(wp.total_trades))
    table.add_row("Unique Markets", str(wp.unique_markets))
    table.add_row(
        "Total Volume", f"${wp.total_usdc_volume:,.2f}",
    )
    table.add_row(
        "Buy/Sell", f"{wp.buy_count} / {wp.sell_count}",
    )
    if wp.first_seen:
        table.add_row(
            "First Seen",
            wp.first_seen.strftime("%Y-%m-%d %H:%M UTC"),
        )
    if wp.last_seen:
        table.add_row(
            "Last Seen",
            wp.last_seen.strftime("%Y-%m-%d %H:%M UTC"),
        )
    if wp.first_seen and wp.last_seen:
        age = wp.last_seen - wp.first_seen
        table.add_row("Account Age", f"{age.days} days")

    console.print(Panel(table, expand=False))


@main.command()
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
@click.option(
    "--since", type=int, default=3600,
    help="Lookback window in seconds (default: 3600 = 1 hour)",
)
@click.option(
    "--min-wallets", type=int, default=3,
    help="Minimum distinct wallets to form a cluster",
)
@click.option(
    "--max-price", type=float, default=0.20,
    help="Maximum price to consider as minority side",
)
@click.option(
    "--min-confidence", type=float, default=0.3,
    help="Minimum confidence to display (0.0-1.0)",
)
def clusters(
    config_path: str | None,
    since: int,
    min_wallets: int,
    max_price: float,
    min_confidence: float,
) -> None:
    """Detect coordinated entry patterns in recent trades."""
    settings = load_settings(config_path=config_path)
    asyncio.run(_show_clusters(
        settings, since, min_wallets, max_price, min_confidence,
    ))


async def _show_clusters(
    settings: Settings,
    lookback: int,
    min_wallets: int,
    max_price: float,
    min_confidence: float,
) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    detector = CoordinatedEntryDetector(
        lookback_seconds=lookback,
        min_wallets=min_wallets,
        max_price=max_price,
        min_confidence=min_confidence,
    )

    try:
        entries = await detector.scan(db)
    finally:
        await db.close()

    console = Console()

    if not entries:
        console.print(
            "[yellow]No coordinated entry patterns detected "
            f"in the last {lookback // 60} minutes.[/]"
        )
        return

    console.print(
        f"\n[bold]Found {len(entries)} coordinated entry pattern(s) "
        f"(last {lookback // 60} min):[/]\n"
    )

    for i, entry in enumerate(entries, 1):
        from datetime import UTC, datetime

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Field", style="bold")
        table.add_column("Value")

        table.add_row("Market", entry.market_title or entry.condition_id[:16])
        table.add_row("Outcome", entry.outcome or "N/A")
        table.add_row("Avg Price", f"{entry.avg_price:.1%}")
        table.add_row("Wallets", str(len(entry.wallets)))
        table.add_row("Fresh Wallets", str(entry.fresh_wallet_count))
        table.add_row("Total USDC", f"${entry.total_usdc:,.2f}")
        table.add_row("Trades", str(entry.trade_count))
        spread_min = entry.time_spread_seconds / 60
        table.add_row("Time Spread", f"{spread_min:.1f} min")

        first_dt = datetime.fromtimestamp(entry.first_entry, tz=UTC)
        last_dt = datetime.fromtimestamp(entry.last_entry, tz=UTC)
        table.add_row(
            "Window",
            f"{first_dt.strftime('%H:%M:%S')} — "
            f"{last_dt.strftime('%H:%M:%S')} UTC",
        )

        conf_color = (
            "red" if entry.confidence >= 0.7
            else "yellow" if entry.confidence >= 0.5
            else "blue"
        )
        table.add_row(
            "Confidence",
            f"[bold {conf_color}]{entry.confidence:.0%}[/]",
        )

        # Show truncated wallet list
        shown = entry.wallets[:5]
        wallet_lines = [
            f"  {w[:6]}...{w[-4:]}" for w in shown
        ]
        if len(entry.wallets) > 5:
            wallet_lines.append(
                f"  ... and {len(entry.wallets) - 5} more"
            )
        table.add_row("Wallet List", "\n".join(wallet_lines))

        border = (
            "red" if entry.confidence >= 0.7
            else "yellow" if entry.confidence >= 0.5
            else "blue"
        )
        panel = Panel(
            table,
            title=f"[bold {border}]Pattern #{i}[/]",
            border_style=border,
            expand=False,
        )
        console.print(panel)


# --- Historical analysis commands ---


@main.command()
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
def stats(config_path: str | None) -> None:
    """Show aggregate statistics from the local database."""
    settings = load_settings(config_path=config_path)
    asyncio.run(_show_stats(settings))


async def _show_stats(settings: Settings) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    try:
        s = await db.get_global_stats()
        alert_count = await db.get_alert_count()
        top_markets = await db.get_top_markets(5)
        top_wallets = await db.get_top_wallets(5)
    finally:
        await db.close()

    console = Console()

    if not s:
        console.print("[yellow]No trades in database.[/]")
        return

    from datetime import UTC, datetime

    # Overview
    overview = Table(
        title="Database Overview",
        show_header=False, box=None, padding=(0, 2),
    )
    overview.add_column("Field", style="bold")
    overview.add_column("Value")

    overview.add_row("Total Trades", f"{s['total_trades']:,}")
    overview.add_row("Unique Wallets", f"{s['unique_wallets']:,}")
    overview.add_row("Unique Markets", f"{s['unique_markets']:,}")
    overview.add_row("Total Volume", f"${s['total_volume']:,.2f}")
    overview.add_row("Avg Trade Size", f"${s['avg_trade_size']:,.2f}")
    overview.add_row("Buy / Sell", f"{s['buys']:,} / {s['sells']:,}")
    overview.add_row("Alerts Generated", str(alert_count))

    if s.get("first_trade"):
        first = datetime.fromtimestamp(s["first_trade"], tz=UTC)
        last = datetime.fromtimestamp(s["last_trade"], tz=UTC)
        overview.add_row("First Trade", first.strftime("%Y-%m-%d %H:%M UTC"))
        overview.add_row("Last Trade", last.strftime("%Y-%m-%d %H:%M UTC"))
        span = last - first
        overview.add_row("Time Span", f"{span.days} days")

    overview.add_row(
        "DB File", str(settings.resolved_db_path),
    )
    console.print(Panel(overview, expand=False))

    # Top markets
    if top_markets:
        console.print()
        mt = Table(title="Top Markets by Volume")
        mt.add_column("#", style="dim")
        mt.add_column("Market")
        mt.add_column("Volume", justify="right")
        mt.add_column("Trades", justify="right")
        mt.add_column("Wallets", justify="right")

        for i, m in enumerate(top_markets, 1):
            name = m["market_name"]
            if len(name) > 50:
                name = name[:47] + "..."
            mt.add_row(
                str(i), name,
                f"${m['total_volume']:,.0f}",
                str(m["trade_count"]),
                str(m["unique_wallets"]),
            )
        console.print(mt)

    # Top wallets
    if top_wallets:
        console.print()
        wt = Table(title="Top Wallets by Volume")
        wt.add_column("#", style="dim")
        wt.add_column("Wallet")
        wt.add_column("Pseudonym")
        wt.add_column("Volume", justify="right")
        wt.add_column("Trades", justify="right")
        wt.add_column("Markets", justify="right")

        for i, w in enumerate(top_wallets, 1):
            addr = w["proxy_wallet"]
            short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
            wt.add_row(
                str(i), short,
                w["pseudonym"] or "(anon)",
                f"${w['total_volume']:,.0f}",
                str(w["trade_count"]),
                str(w["unique_markets"]),
            )
        console.print(wt)


@main.command()
@click.argument("slug")
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
@click.option(
    "--limit", type=int, default=20,
    help="Number of recent trades to show",
)
def market(slug: str, config_path: str | None, limit: int) -> None:
    """Show recent trades for a specific market slug."""
    settings = load_settings(config_path=config_path)
    asyncio.run(_show_market(settings, slug, limit))


async def _show_market(settings: Settings, slug: str, limit: int) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    try:
        trades = await db.get_market_trades(slug, limit)
    finally:
        await db.close()

    console = Console()

    if not trades:
        console.print(f"[yellow]No trades found for market '{slug}'.[/]")
        return

    title = trades[0].title or slug
    console.print(f"\n[bold]Market:[/] {title}")
    console.print(f"[bold]Slug:[/] {slug}")
    console.print(f"[bold]Showing:[/] {len(trades)} most recent trades\n")

    table = Table()
    table.add_column("Time", style="dim")
    table.add_column("Side")
    table.add_column("Outcome")
    table.add_column("Price", justify="right")
    table.add_column("Size", justify="right")
    table.add_column("USDC", justify="right")
    table.add_column("Wallet")

    for t in trades:
        side_color = "green" if t.side == "BUY" else "red"
        addr = t.proxy_wallet
        short_wallet = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
        table.add_row(
            t.trade_time.strftime("%m-%d %H:%M"),
            f"[{side_color}]{t.side}[/]",
            t.outcome,
            f"${t.price:.3f}",
            f"{t.size:,.0f}",
            f"${t.usdc_value:,.2f}",
            short_wallet,
        )

    console.print(table)


@main.command()
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
@click.option(
    "--limit", type=int, default=20,
    help="Number of recent alerts to show",
)
def alerts(config_path: str | None, limit: int) -> None:
    """Show recent alerts from the database."""
    settings = load_settings(config_path=config_path)
    asyncio.run(_show_alerts(settings, limit))


async def _show_alerts(settings: Settings, limit: int) -> None:
    db = Database(settings.resolved_db_path)
    await db.initialize()

    try:
        recent = await db.get_recent_alerts(limit)
    finally:
        await db.close()

    console = Console()

    if not recent:
        console.print("[yellow]No alerts in database.[/]")
        return

    console.print(f"\n[bold]Recent Alerts[/] (showing {len(recent)}):\n")

    table = Table()
    table.add_column("Time", style="dim")
    table.add_column("Impact")
    table.add_column("Score", justify="right")
    table.add_column("Market")
    table.add_column("Outcome")
    table.add_column("USDC", justify="right")
    table.add_column("Wallet")

    impact_style = {
        "high": "bold red",
        "medium": "bold yellow",
        "low": "bold blue",
    }

    for a in recent:
        style = impact_style.get(a["impact"], "")
        title = a["title"]
        if len(title) > 35:
            title = title[:32] + "..."
        addr = a["proxy_wallet"]
        short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 12 else addr
        table.add_row(
            str(a["created_at"])[:19],
            f"[{style}]{a['impact'].upper()}[/]",
            f"{a['composite_score']:.2f}",
            title,
            f"{a['outcome']} ({a['side']})",
            f"${a['usdc_value']:,.0f}",
            short,
        )

    console.print(table)


# --- Config management commands ---


@main.group(name="config")
def config_group() -> None:
    """Configuration management."""


@config_group.command(name="show")
@click.option(
    "--config", "config_path", default=None,
    help="Path to config.toml",
)
def config_show(config_path: str | None) -> None:
    """Display the current effective configuration."""
    settings = load_settings(config_path=config_path)
    console = Console()

    console.print("\n[bold]Effective Configuration[/]\n")

    # General
    gt = Table(title="General", show_header=False, box=None, padding=(0, 2))
    gt.add_column("Field", style="bold")
    gt.add_column("Value")
    gt.add_row("DB Path", str(settings.resolved_db_path))
    gt.add_row("Poll Interval", f"{settings.poll_interval_seconds}s")
    gt.add_row("Log Level", settings.log_level)
    console.print(Panel(gt, expand=False))

    # Thresholds
    t = settings.thresholds
    tt = Table(title="Thresholds", show_header=False, box=None, padding=(0, 2))
    tt.add_column("Field", style="bold")
    tt.add_column("Value")
    tt.add_row("Absolute Size (USDC)", f"${t.absolute_size_usd:,.0f}")
    tt.add_row("Z-Score Threshold", str(t.z_score_threshold))
    tt.add_row("Rolling Window", f"{t.rolling_window_trades} trades")
    tt.add_row("Alert Threshold", str(t.alert_threshold))
    tt.add_row("Timing Window", f"{t.timing_window_hours}h")
    tt.add_row("Minority Price", str(t.minority_price_threshold))
    tt.add_row("New Wallet Days", str(t.new_wallet_days))
    tt.add_row("Min Trades (Established)", str(t.min_trades_established))
    tt.add_row("Min Markets (Diverse)", str(t.min_markets_diverse))
    tt.add_row("Win Rate Min Trades", str(t.win_rate_min_trades))
    tt.add_row("Low Prob Threshold", str(t.low_prob_threshold))
    tt.add_row("Prob Size Amplifier", f"${t.prob_size_amplifier:,.0f}")
    tt.add_row("Coordination Lookback", f"{t.coordination_lookback_seconds}s")
    tt.add_row("Coordination Min Wallets", str(t.coordination_min_wallets))
    tt.add_row("Coordination Max Price", str(t.coordination_max_price))
    tt.add_row("Coordination Fresh Threshold", str(t.coordination_fresh_threshold))
    tt.add_row("Coordination Tight Window", f"{t.coordination_tight_window}s")
    tt.add_row("Coordination Min Confidence", str(t.coordination_min_confidence))
    console.print(Panel(tt, expand=False))

    # Scoring weights
    w = settings.scoring
    wt = Table(
        title="Scoring Weights", show_header=False, box=None, padding=(0, 2),
    )
    wt.add_column("Scorer", style="bold")
    wt.add_column("Weight")
    wt.add_row("Trade Size", f"{w.trade_size_weight:.2f}")
    wt.add_row("Timing", f"{w.timing_weight:.2f}")
    wt.add_row("Account Age", f"{w.account_age_weight:.2f}")
    wt.add_row("Win Rate", f"{w.win_rate_weight:.2f}")
    wt.add_row("Probability", f"{w.probability_weight:.2f}")
    wt.add_row("Coordination", f"{w.coordination_weight:.2f}")
    console.print(Panel(wt, expand=False))

    # Alerting
    at = Table(title="Alerting", show_header=False, box=None, padding=(0, 2))
    at.add_column("Field", style="bold")
    at.add_column("Value")
    at.add_row("Sinks", ", ".join(settings.alerting.sinks))
    if settings.alerting.discord_webhook_url:
        at.add_row("Discord URL", "***configured***")
    if settings.alerting.telegram_bot_token:
        at.add_row("Telegram Bot", "***configured***")
        at.add_row("Telegram Chat ID", settings.alerting.telegram_chat_id)
    console.print(Panel(at, expand=False))

    # Market filter
    mf = settings.markets
    ft = Table(
        title="Market Filter", show_header=False, box=None, padding=(0, 2),
    )
    ft.add_column("Field", style="bold")
    ft.add_column("Value")
    if mf.watch_slugs:
        ft.add_row("Watch Slugs", ", ".join(mf.watch_slugs))
    else:
        ft.add_row("Watch Slugs", "(all markets)")
    ft.add_row(
        "Exclude Patterns",
        ", ".join(mf.exclude_slug_patterns[:5])
        + (
            f" ... +{len(mf.exclude_slug_patterns) - 5} more"
            if len(mf.exclude_slug_patterns) > 5
            else ""
        ),
    )
    console.print(Panel(ft, expand=False))


@config_group.command(name="init")
@click.option(
    "--path", default="config.toml",
    help="Where to write the config file",
)
def config_init(path: str) -> None:
    """Generate a default config.toml file."""
    from pathlib import Path

    dest = Path(path)
    if dest.exists():
        click.echo(f"Error: {dest} already exists. Remove it first.")
        raise SystemExit(1)

    template = '''\
# Whale Detector configuration
# See README.md for full documentation

[general]
db_path = "~/.local/share/whale-detector/trades.db"
poll_interval_seconds = 5
log_level = "INFO"

[thresholds]
absolute_size_usd = 10000
z_score_threshold = 3.0
rolling_window_trades = 500
alert_threshold = 0.5
timing_window_hours = 24.0
minority_price_threshold = 0.35
new_wallet_days = 7.0
min_trades_established = 10
min_markets_diverse = 3
win_rate_min_trades = 5
low_prob_threshold = 0.15
prob_size_amplifier = 1000.0
coordination_lookback_seconds = 3600
coordination_min_wallets = 3
coordination_max_price = 0.20
coordination_fresh_threshold = 5
coordination_tight_window = 1800
coordination_min_confidence = 0.4

[scoring]
trade_size_weight = 0.25
timing_weight = 0.15
account_age_weight = 0.15
win_rate_weight = 0.10
probability_weight = 0.15
coordination_weight = 0.20

[alerting]
sinks = ["terminal"]
# discord_webhook_url = "https://discord.com/api/webhooks/..."
# telegram_bot_token = "123456:ABC-DEF..."
# telegram_chat_id = "-1001234567890"

[markets]
watch_slugs = []
exclude_slug_patterns = [
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
'''
    dest.write_text(template)
    click.echo(f"Created {dest}")
