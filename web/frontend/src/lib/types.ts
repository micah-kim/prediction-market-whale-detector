export interface GlobalStats {
  total_trades: number;
  unique_wallets: number;
  unique_markets: number;
  total_volume: number;
  first_trade: number | null;
  last_trade: number | null;
  avg_trade_size: number;
  buys: number;
  sells: number;
  alert_count: number;
}

export interface TopMarket {
  condition_id: string;
  market_name: string;
  trade_count: number;
  unique_wallets: number;
  total_volume: number;
}

export interface TopWallet {
  proxy_wallet: string;
  pseudonym: string;
  trade_count: number;
  unique_markets: number;
  total_volume: number;
}

export interface Trade {
  transaction_hash: string;
  proxy_wallet: string;
  side: string;
  asset: string;
  condition_id: string;
  size: number;
  price: number;
  usdc_value: number;
  timestamp: number;
  title: string;
  slug: string;
  event_slug: string;
  outcome: string;
  outcome_index: number;
  pseudonym: string;
  trade_time: string;
}

export interface AlertRecord {
  composite_score: number;
  impact: string;
  scores_json: string;
  reasons_json: string;
  created_at: string;
  title: string;
  slug: string;
  outcome: string;
  side: string;
  usdc_value: number;
  proxy_wallet: string;
  pseudonym: string;
}

export interface WalletProfile {
  address: string;
  first_seen: string | null;
  last_seen: string | null;
  total_trades: number;
  unique_markets: number;
  total_usdc_volume: number;
  buy_count: number;
  sell_count: number;
  pseudonym: string;
}

export interface CoordinatedEntry {
  condition_id: string;
  market_title: string;
  market_slug: string;
  outcome: string;
  avg_price: number;
  wallets: string[];
  fresh_wallet_count: number;
  total_usdc: number;
  time_spread_seconds: number;
  first_entry: number;
  last_entry: number;
  confidence: number;
  trade_count: number;
}

export type ImpactLevel = "high" | "medium" | "low";
