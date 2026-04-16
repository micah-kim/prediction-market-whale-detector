# Whale Detection Metrics

These are the core signals for detecting potentially insider-informed or whale-driven
trades. This file is the primary reference for building detection algorithms.

## 1. Large Trade Size

Outsized bets far above normal volume, especially just before an event outcome or news
break.

- **Example**: Four accounts bet >$30M on 2024 US election to drive Trump odds sharply
  higher.
- **Implementation**: Compare trade size against rolling average/stddev for that market.
  Flag trades exceeding a configurable threshold (e.g. 3+ standard deviations).

## 2. Timing of Bets

Well-timed trades in final hours/minutes before a surprise event resolution.

- **Example**: Dozens of wallets poured funds into Iran ceasefire markets hours before a
  sudden truce announcement.
- **Implementation**: Track time-to-resolution for each trade. Flag trades placed within
  a configurable window before surprise outcomes.

## 3. New or Anonymous Accounts

Brand-new wallets with minimal history that appear solely to place a specific
high-conviction bet, then cash out.

- **Example**: Multiple fresh wallets betting exclusively on one outcome and immediately
  profiting.
- **Implementation**: Track wallet age, transaction count, and diversity of markets
  traded. Flag wallets with age < threshold AND single-market activity AND profit > threshold.

## 4. High Win Rate

Wallets with near-perfect records on unlikely outcomes.

- **Example**: Linked accounts betting only on Iran/Venezuela outcomes with 100% success
  rate, netting >$1.6M.
- **Implementation**: Calculate per-wallet win rate weighted by outcome probability.
  Flag wallets with statistically improbable win streaks (e.g. p < 0.01 under random
  chance).

## 5. Coordinated Activity

Clusters of wallets acting in sync (similar bets at similar times) that converge funds
to the same destination.

- **Example**: ~36 wallets made identical geopolitical bets, cashed out to one exchange
  address.
- **Implementation**: Cluster wallets by temporal correlation, bet similarity, and
  fund-flow graph analysis. Flag groups with high behavioral similarity.

## Composite Scoring

Combine metrics into a weighted anomaly score per wallet/trade. A single flag is
suggestive; multiple flags are strongly indicative. Suggested approach:

```
anomaly_score = w1 * trade_size_z + w2 * timing_score + w3 * account_age_score
              + w4 * win_rate_anomaly + w5 * coordination_score
```

Thresholds and weights should be tunable and empirically calibrated.
