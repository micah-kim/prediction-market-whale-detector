# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Prediction Market Whale Detector — a Python CLI tool for identifying and tracking large traders ("whales") on Polymarket prediction markets. Monitors real-time trades via the Polymarket Data API, scores them for anomalies, and alerts on whale activity.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                    # run tests
ruff check src/           # lint
whale-detector monitor    # start monitoring (use --threshold 100 for testing)
```

## Architecture

Pipeline: Data API polling → Pydantic normalization → SQLite persistence → pluggable scorer pipeline → alert sinks (terminal).

Key modules in `src/whale_detector/`:
- `models.py` — Trade, Alert, ScoreResult data models
- `config.py` — Settings with TOML + env var + CLI override loading
- `api/` — Async HTTP client with rate limiting; Data API and Gamma API wrappers
- `scoring/` — Scorer protocol + CompositeScorer; TradeSizeScorer (more scorers in Phase 2+)
- `db.py` — SQLite persistence via aiosqlite
- `monitor.py` — Async polling loop with clean shutdown
- `alerting/` — AlertSink protocol; Rich terminal output
- `cli.py` — Click CLI entry point

## Research Files

Background research lives in `docs/research/`. Read these before making design or implementation decisions:

- `01-prediction-markets-overview.md` — How decentralized prediction markets work (mechanics, token pricing, blockchain settlement)
- `02-polymarket-architecture.md` — Polymarket's hybrid CLOB/on-chain architecture and trade flow
- `03-whale-detection-metrics.md` — Core signals for detecting whale/insider trades (primary reference for detection algorithms)
- `04-case-studies.md` — Real-world examples of whale bets and suspected insider trading (2024 election, Venezuela, etc.)
- `05-monitoring-and-mitigation.md` — Current surveillance tools and mitigation strategies
