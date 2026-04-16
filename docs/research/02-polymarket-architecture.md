# Polymarket Architecture

## Hybrid Infrastructure

Polymarket runs a **hybrid model**:
- **Off-chain**: Central Limit Order Book (CLOB) for fast trade matching. Shifted from
  AMM model in 2024 to attract deeper liquidity.
- **On-chain**: Settlement on Polygon blockchain for security and transparency.

## Trade Flow

1. Trader connects crypto wallet (or Polymarket-provided wallet).
2. Deposits USDC (1:1 to USD).
3. Buys/sells YES/NO shares at current order book prices.
4. Outcome tokens (ERC-1155) represent positions.
5. On resolution, winning tokens are redeemable for USDC.

## Fee Structure

- **Makers**: Receive rebates (incentivizes liquidity provision).
- **Takers**: Pay ~2% fee, only on winning bets.

## Market Microstructure

- Prices between $0.01 and $0.99, dynamically adjusted by supply-demand.
- Arbitrage keeps Yes+No prices summing to ~$1.00.
- Professional market makers provide thick order books with low spreads.
- ~70% of trades executed by bots/algorithms (as of 2025).
- Cross-platform arbitrage keeps odds aligned with Kalshi, CME.

## Scale

- 2024 US election: >$3.5B in volume.
- Early 2026: monthly crypto prediction market volumes exceeded $20B.
- Geopolitical and macro events are top volume drivers.
