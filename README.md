# Prediction Market Whale Detector

A Python CLI tool + web dashboard that monitors [Polymarket](https://polymarket.com) trades in real-time, scores them for anomalies, and alerts on whale activity. No API keys required — uses Polymarket's public Data API.

## Quick Start

### Prerequisites

- **Python 3.11+** — check with `python3 --version`
- **Node.js 18+** — only needed for the web dashboard, check with `node --version`
- **Git** — to clone the repo

### 1. Clone and install

```bash
git clone https://github.com/your-user/prediction-market-whale-detector.git
cd prediction-market-whale-detector

# Create a virtual environment and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
```

### 2. Generate a config file (optional)

The tool works out of the box with sensible defaults. If you want to customize settings:

```bash
whale-detector config init
```

This creates `config.toml` in the current directory. See [Configuration](#configuration) below for all options.

### 3. Start monitoring

```bash
whale-detector monitor
```

You should see output like:

```
INFO     Database initialized at ~/.local/share/whale-detector/trades.db
INFO     Starting trade monitor (poll every 5s, threshold 0.50)
INFO     Processed 39 new trades
INFO     Processed 34 new trades
```

The monitor will:
- Poll Polymarket's public trade API every 5 seconds
- Store all trades in a local SQLite database
- Score each trade through 6 detection algorithms
- Print alerts to the terminal when a trade's composite score exceeds 0.50

**Note:** You may see gaps of 1-3 minutes between log entries. This is normal — the monitor processes and scores each trade individually, and with pagination fetching up to 500 trades per cycle, processing can take time. The 5-second poll interval starts *after* processing completes.

Press `Ctrl+C` to stop cleanly.

### 4. Check what was collected

```bash
# Aggregate stats
whale-detector stats

# Recent alerts
whale-detector alerts

# Trades for a specific market
whale-detector market <SLUG>

# Wallet profile
whale-detector profile <ADDRESS>

# Coordinated entry patterns
whale-detector clusters
```

### 5. Launch the web dashboard (optional)

The web dashboard is a separate viewer that reads the same SQLite database. You need three terminals:

```bash
# Terminal 1: Keep the monitor running
source .venv/bin/activate
whale-detector monitor

# Terminal 2: Start the API server
source .venv/bin/activate
uvicorn web.backend.main:app --reload --port 8000

# Terminal 3: Start the frontend
cd web/frontend
npm install    # first time only
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to see the dashboard.

The API is also browsable at [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI).

---

## How It Works

```
Data API Polling (GET /trades, paginated)
  -> Pydantic Normalization
  -> SQLite Dedup & Persistence
  -> Per-Market Rolling Statistics
  -> Pluggable Scorer Pipeline (weighted composite)
  -> Coordinated Entry Detection (periodic batch scan)
  -> Alert Sinks (terminal, Discord, Telegram)
```

1. **Fetch** — Polls `data-api.polymarket.com/trades` every N seconds (default 5) with automatic pagination to avoid missing trades during busy periods. No authentication required.
2. **Normalize** — Raw JSON is parsed into `Trade` models with computed USDC value (`size * price`).
3. **Deduplicate** — Each trade is keyed by `transaction_hash` in SQLite. Duplicates are skipped.
4. **Score** — Every new trade passes through 6 independent scorers, each producing a score in [0, 1] with an explanation. A weighted `CompositeScorer` combines them into a final score.
5. **Coordination Detection** — Every 5 minutes, a batch scan checks for bursts of fresh wallets buying minority-side outcomes in the same market within tight time windows.
6. **Alert** — Trades exceeding the alert threshold (default 0.5) are sent to configured sinks (terminal, Discord webhook, Telegram bot).

### Detection Metrics

| Scorer | Weight | Signal |
|--------|--------|--------|
| **Trade Size** | 25% | Absolute USDC threshold ($10K default) or z-score vs. per-market rolling statistics |
| **Coordination** | 20% | Wallet belongs to a detected coordinated entry pattern (multiple fresh wallets, same minority outcome, tight time window) |
| **Timing** | 15% | Proximity to market resolution. Minority outcome bets near close get a 1.5x boost |
| **Account Age** | 15% | Fresh wallets, low trade counts, single-market activity |
| **Probability** | 15% | Large BUY orders on outcomes priced below 15 cents (long-shot bets at scale) |
| **Win Rate** | 10% | Wallets consistently buying extreme long shots across multiple markets |

Each scorer's weight is configurable. The composite score determines impact level: **HIGH** (>=0.8), **MEDIUM** (>=0.5), **LOW** (<0.5).

### Coordinated Entry Detection

Instead of scoring trades individually, the coordination detector looks for groups of wallets acting in concert:

- Scans for markets where 3+ distinct wallets bought minority-side outcomes (price < 20%) within the last hour
- Checks what fraction of those wallets are "fresh" (fewer than 5 prior trades)
- Scores confidence based on: number of wallets, freshness ratio, time spread tightness, and price extremity
- Detected patterns boost the coordination score of every subsequent trade from those wallets

### Market Filtering

High-frequency micro markets (BTC/ETH up/down, temperature markets) are excluded by default to reduce noise. You can customize exclusion patterns or restrict monitoring to specific market slugs.

---

## CLI Reference

### `whale-detector monitor`

Start real-time trade monitoring.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--config` | PATH | auto-detect | Path to `config.toml` |
| `--threshold` | FLOAT | 0.5 | Alert threshold (0.0-1.0) |
| `--poll-interval` | INT | 5 | Seconds between API polls |
| `--min-size` | FLOAT | 10000 | Minimum USDC trade size to flag |
| `--fresh-wallets-only` | INT | off | Only alert on wallets with fewer than N prior trades |
| `--log-level` | TEXT | INFO | Logging level (DEBUG, INFO, WARNING, ERROR) |

Examples:

```bash
# Default monitoring
whale-detector monitor

# Lower thresholds for testing — you'll see more alerts
whale-detector monitor --threshold 0.1 --min-size 100

# Only flag trades from wallets with < 5 prior trades
whale-detector monitor --fresh-wallets-only 5

# Verbose logging — see every API call and scoring decision
whale-detector monitor --log-level DEBUG
```

### `whale-detector clusters`

Detect coordinated entry patterns in recent trades.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--since` | INT | 3600 | Lookback window in seconds |
| `--min-wallets` | INT | 3 | Minimum distinct wallets to form a cluster |
| `--max-price` | FLOAT | 0.20 | Maximum price to consider as minority side |
| `--min-confidence` | FLOAT | 0.3 | Minimum confidence to display |

### `whale-detector stats`

Show aggregate statistics from the local database: total trades, unique wallets/markets, volume, top markets, top wallets.

```bash
whale-detector stats [--config PATH]
```

### `whale-detector market <SLUG>`

Show recent trades for a specific market.

```bash
whale-detector market <SLUG> [--limit 20] [--config PATH]
```

### `whale-detector alerts`

Show recent alerts from the database.

```bash
whale-detector alerts [--limit 20] [--config PATH]
```

### `whale-detector profile <ADDRESS>`

Display a wallet's trading profile from the local database.

```bash
whale-detector profile <ADDRESS> [--config PATH]
```

### `whale-detector config`

Configuration management.

```bash
whale-detector config show [--config PATH]   # Display effective config
whale-detector config init [--path FILE]     # Generate default config.toml
```

---

## Web Dashboard

The web dashboard provides a visual layer on top of the CLI monitor. It reads the same SQLite database (via WAL mode for safe concurrent access).

### Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | `/` | Summary cards, top markets/wallets tables |
| Live Feed | `/live` | Auto-refreshing stream of recent alerts (5s polling) |
| Alerts | `/alerts` | Full alerts history table, sortable |
| Coordination | `/coordination` | Detected coordinated entry patterns |
| Markets | `/markets` | All tracked markets, click through to detail view |
| Paper Trading | `/paper-trading` | Simulated positions tracking (see below) |
| Settings | `/settings` | Read-only view of effective config |

### Paper Trading

The paper trading system auto-follows whale alerts with simulated positions to validate whether the detection engine produces alpha.

Enable it in `config.toml`:

```toml
[paper_trading]
enabled = true
initial_bankroll = 10000.0
risk_per_trade_pct = 0.02
min_alert_score = 0.5
```

When enabled, every alert above `min_alert_score` automatically creates a paper trade with bankroll-based position sizing. Positions are settled when markets resolve via the Gamma API.

### API Endpoints

The backend exposes these REST endpoints at `http://localhost:8000`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/stats` | Global stats + alert count |
| `GET /api/stats/top-markets` | Markets ranked by volume |
| `GET /api/stats/top-wallets` | Wallets ranked by volume |
| `GET /api/alerts` | Recent alerts (supports `?limit=`) |
| `GET /api/alerts/live` | Last 10 alerts |
| `GET /api/markets/{slug}` | Trades for a market |
| `GET /api/wallets/{address}` | Wallet profile |
| `GET /api/coordination` | Current coordination patterns |
| `GET /api/config` | Effective configuration |
| `GET /api/paper/summary` | Paper trading stats |
| `GET /api/paper/positions` | Paper trades (`?status=open\|won\|lost`) |
| `POST /api/paper/reset` | Reset paper trading data |

---

## Configuration

Settings are loaded with this precedence (highest first):

1. CLI flags (`--threshold`, etc.)
2. Environment variables (`WHALE_DETECTOR_*`)
3. TOML config file
4. Built-in defaults

### Config File Search

If `--config` is not specified, the tool looks for:
1. `./config.toml`
2. `~/.config/whale-detector/config.toml`

Use `whale-detector config init` to generate a default config file.

### Environment Variables

Use the `WHALE_DETECTOR_` prefix. Nested sections use double underscores:

```bash
export WHALE_DETECTOR_POLL_INTERVAL_SECONDS=10
export WHALE_DETECTOR_THRESHOLDS__ABSOLUTE_SIZE_USD=5000
export WHALE_DETECTOR_LOG_LEVEL=DEBUG
```

### Alert Sinks

Configure where alerts are delivered in `config.toml`:

```toml
[alerting]
sinks = ["terminal", "discord", "telegram"]

# Discord webhook
discord_webhook_url = "https://discord.com/api/webhooks/..."

# Telegram bot
telegram_bot_token = "123456:ABC-DEF..."
telegram_chat_id = "-1001234567890"
```

Multiple sinks can be active simultaneously. Terminal is always the fallback.

### Full Config Reference

Run `whale-detector config show` to see all effective values, or see `config.example.toml`. Key sections:

```toml
[general]
db_path = "~/.local/share/whale-detector/trades.db"
poll_interval_seconds = 5
log_level = "INFO"

[thresholds]
absolute_size_usd = 10000
z_score_threshold = 3.0
rolling_window_trades = 500
alert_threshold = 0.5
coordination_lookback_seconds = 3600
coordination_min_wallets = 3
coordination_max_price = 0.20

[scoring]
trade_size_weight = 0.25
timing_weight = 0.15
account_age_weight = 0.15
win_rate_weight = 0.10
probability_weight = 0.15
coordination_weight = 0.20

[alerting]
sinks = ["terminal"]

[markets]
watch_slugs = []
exclude_slug_patterns = ["btc-above-*", "eth-above-*", ...]

[paper_trading]
enabled = false
initial_bankroll = 10000.0
risk_per_trade_pct = 0.02
min_alert_score = 0.5
```

---

## Data Storage

All trade data and alerts are stored locally in SQLite at `~/.local/share/whale-detector/trades.db` (configurable). No data leaves your machine unless you configure Discord/Telegram alert sinks.

Storage estimate: ~1.2 GB/year at 10K trades/day.

The database uses WAL (Write-Ahead Logging) mode so the monitor can write while the web dashboard reads concurrently.

## Troubleshooting

### Monitor seems slow / timestamps are minutes apart

This is expected. Each poll cycle fetches up to 500 trades (paginated), then processes each one individually — deduplication, insertion, and scoring. The 5-second poll interval only starts *after* processing completes. With high trade volume, a single cycle can take 1-3 minutes.

### No alerts showing

Most trades score below the default 0.50 threshold. This means no whale-like activity is being detected. To verify scoring is working, lower the threshold:

```bash
whale-detector monitor --threshold 0.1 --min-size 100
```

### Web dashboard shows "Loading..." or errors

Make sure all three processes are running:
1. `whale-detector monitor` (writes to the database)
2. `uvicorn web.backend.main:app --reload --port 8000` (API server)
3. `cd web/frontend && npm run dev` (frontend at port 3000)

The API must be on port 8000 and the frontend on port 3000 for CORS to work.

### Database location

Default: `~/.local/share/whale-detector/trades.db`. Check with:

```bash
whale-detector config show
```

## Development

```bash
source .venv/bin/activate
pytest                    # run tests (115 tests)
ruff check src/ web/      # lint Python
cd web/frontend && npm run build  # type-check frontend
```
