# Decentralized Prediction Markets: Overview

## What They Are

Decentralized prediction markets are blockchain-based platforms where users trade on
outcomes of real-world events using cryptocurrency. Traders buy "Yes" or "No" outcome
tokens priced $0-$1, where price equals market-implied probability (e.g. $0.72 = ~72%
chance).

## Core Mechanics

- **Token model**: Each market issues binary outcome tokens (ERC-1155 Conditional Tokens
  via Gnosis). Correct tokens pay $1.00; incorrect expire worthless.
- **Settlement**: Blockchain smart contracts handle token minting, custody of stakes
  (USDC stablecoin), and payout distribution -- trustless, no intermediary.
- **Oracle resolution**: Polymarket uses UMA's Optimistic Oracle. Anyone can propose a
  result; 2-4 hour challenge window. If disputed, UMA token holders vote (resolves in
  ~2-3 days).
- **No leverage**: Each share is fully paid upfront.

## Why Decentralized

- Funds stay in on-chain custody (can't be seized or mismanaged).
- Politically sensitive markets can operate without censorship.
- Decentralized resolution guards against single-point failure.
- All trades, positions, and payouts are on a public ledger.

## Key Platforms

| Platform   | Type         | Chain   | Notes                          |
|------------|--------------|---------|--------------------------------|
| Polymarket | Decentralized| Polygon | Largest by volume, hybrid CLOB |
| Kalshi     | Regulated    | N/A     | US-regulated, traditional      |
| CME        | Traditional  | N/A     | Cross-platform arbitrage target|
