# Monitoring and Mitigation Strategies

## Current Surveillance Landscape

- Academic researchers and analytics firms comb Polymarket's blockchain for abnormal
  patterns.
- Automated tools (Dune dashboards, Lookonchain alerts) flag unusual trading bursts and
  new account clusters.
- Social media plays a role -- suspicious trades are often highlighted publicly for
  investigation.

## Analytics Tools in Use

| Tool            | Purpose                                      |
|-----------------|----------------------------------------------|
| Dune Analytics  | Custom dashboards for on-chain trade analysis|
| Nansen          | Wallet labeling and whale tracking           |
| Lookonchain     | Real-time whale activity alerts              |
| Bubble Maps     | Wallet cluster visualization                 |

## Platform Responses

- **Polymarket**: Partnered with analytic firms, instituted enhanced integrity rules.
  Insider trading explicitly banned. Officials with inside knowledge barred from
  certain markets.
- **Kalshi**: Preemptively barred politicians and athletes from betting on events they
  influence.

## Open Challenges

- Differentiating true insider trades from lucky timing remains difficult.
- Flagged cases rely on circumstantial evidence (wallet anonymity) rather than direct
  proof.
- Regulatory definitions of illicit behavior in decentralized markets are still evolving.

## Data Sources for This Project

- **Polygon blockchain**: All Polymarket trades are on-chain and queryable.
- **Polymarket API**: Market data, order books, trade history.
- **Dune Analytics**: Pre-built and custom SQL queries against decoded contract data.
- **Wallet profiling**: Transaction history, age, funding sources.
- **Fund-flow graphs**: Track where profits move post-cashout.

## Detection Pipeline (Conceptual)

```
Blockchain Data Ingestion
    -> Trade Normalization
    -> Per-Wallet Feature Extraction
    -> Anomaly Scoring (see 03-whale-detection-metrics.md)
    -> Clustering & Graph Analysis
    -> Alert Generation
    -> Human Review / Dashboard
```
