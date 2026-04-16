"use client";

import { useState } from "react";
import Link from "next/link";
import StatCard from "@/components/stat-card";
import { usePolling } from "@/hooks/use-polling";
import { postApi } from "@/lib/api";

interface PaperSummary {
  initial_bankroll: number;
  current_bankroll: number;
  total_deployed: number;
  total_realized_pnl: number;
  open_positions: number;
  won: number;
  lost: number;
  total_trades: number;
  win_rate: number;
  roi: number;
  avg_score_winners: number | null;
  avg_score_losers: number | null;
}

interface PaperTrade {
  id: number;
  alert_id: string;
  condition_id: string;
  market_slug: string;
  market_title: string;
  outcome: string;
  side: string;
  entry_price: number;
  shares: number;
  cost_basis: number;
  exit_price: number | null;
  pnl: number | null;
  status: string;
  created_at: string;
  resolved_at: string | null;
  whale_score: number;
  whale_wallet: string;
}

// condition_id -> { outcome_name: current_price }
type PriceMap = Record<string, Record<string, number>>;

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function truncateWallet(address: string): string {
  if (address.length > 12)
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  return address;
}

export default function PaperTradingPage() {
  const { data: summary, loading: summaryLoading } =
    usePolling<PaperSummary>("/api/paper/summary", 10000);
  const { data: openPositions } = usePolling<PaperTrade[]>(
    "/api/paper/positions?status=open&limit=50",
    10000,
  );
  const { data: closedPositions } = usePolling<PaperTrade[]>(
    "/api/paper/positions?status=won&limit=25",
    30000,
  );
  const { data: lostPositions } = usePolling<PaperTrade[]>(
    "/api/paper/positions?status=lost&limit=25",
    30000,
  );
  const { data: livePrices } = usePolling<PriceMap>(
    "/api/paper/prices",
    30000,
  );
  const [resetting, setResetting] = useState(false);

  const handleReset = async () => {
    if (!confirm("Reset all paper trading data? This cannot be undone.")) {
      return;
    }
    setResetting(true);
    try {
      await postApi("/api/paper/reset");
      window.location.reload();
    } catch {
      alert("Failed to reset paper trading");
    } finally {
      setResetting(false);
    }
  };

  const closedAll = [
    ...(closedPositions ?? []),
    ...(lostPositions ?? []),
  ].sort(
    (a, b) =>
      new Date(b.resolved_at ?? b.created_at).getTime() -
      new Date(a.resolved_at ?? a.created_at).getTime(),
  );

  // Compute unrealized PnL from live prices
  const getUnrealizedPnl = (p: PaperTrade): number | null => {
    if (!livePrices) return null;
    const marketPrices = livePrices[p.condition_id];
    if (!marketPrices) return null;
    const currentPrice = marketPrices[p.outcome];
    if (currentPrice === undefined) return null;
    return (currentPrice - p.entry_price) * p.shares;
  };

  const getCurrentPrice = (p: PaperTrade): number | null => {
    if (!livePrices) return null;
    const marketPrices = livePrices[p.condition_id];
    if (!marketPrices) return null;
    const price = marketPrices[p.outcome];
    return price !== undefined ? price : null;
  };

  // Aggregate unrealized PnL across all open positions
  const totalUnrealizedPnl =
    openPositions?.reduce((sum, p) => {
      const upnl = getUnrealizedPnl(p);
      return sum + (upnl ?? 0);
    }, 0) ?? 0;

  const hasLivePrices = livePrices && Object.keys(livePrices).length > 0;

  if (summaryLoading) {
    return (
      <p className="text-muted-foreground text-sm">
        Loading paper trading data...
      </p>
    );
  }

  const pnl = summary?.total_realized_pnl ?? 0;
  const pnlColor = pnl >= 0 ? "text-success" : "text-destructive";
  const unrealizedColor =
    totalUnrealizedPnl >= 0 ? "text-success" : "text-destructive";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Paper Trading</h2>
        <button
          onClick={handleReset}
          disabled={resetting}
          className="px-3 py-1.5 text-xs bg-destructive/20 text-destructive border border-destructive/30 rounded hover:bg-destructive/30 disabled:opacity-50"
        >
          {resetting ? "Resetting..." : "Reset"}
        </button>
      </div>

      {/* Summary Cards */}
      {summary && Object.keys(summary).length > 0 ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-7 gap-4">
            <StatCard
              title="Bankroll"
              value={formatUsd(summary.current_bankroll)}
            />
            <div className="bg-card border border-border rounded-lg p-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Realized PnL
              </p>
              <p className={`text-2xl font-bold mt-1 ${pnlColor}`}>
                {pnl >= 0 ? "+" : ""}
                {formatUsd(pnl)}
              </p>
            </div>
            <div className="bg-card border border-border rounded-lg p-4">
              <p className="text-xs text-muted-foreground uppercase tracking-wide">
                Unrealized PnL
              </p>
              <p className={`text-2xl font-bold mt-1 ${unrealizedColor}`}>
                {hasLivePrices ? (
                  <>
                    {totalUnrealizedPnl >= 0 ? "+" : ""}
                    {formatUsd(totalUnrealizedPnl)}
                  </>
                ) : (
                  <span className="text-muted-foreground">--</span>
                )}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5">
                updates every 30s
              </p>
            </div>
            <StatCard
              title="Win Rate"
              value={`${(summary.win_rate * 100).toFixed(1)}%`}
              subtitle={`${summary.won}W / ${summary.lost}L`}
            />
            <StatCard
              title="ROI"
              value={`${(summary.roi * 100).toFixed(1)}%`}
            />
            <StatCard
              title="Open Positions"
              value={summary.open_positions}
            />
            <StatCard
              title="Total Trades"
              value={summary.total_trades}
            />
          </div>

          {/* Score Analysis */}
          {(summary.avg_score_winners !== null ||
            summary.avg_score_losers !== null) && (
            <div className="bg-card border border-border rounded-lg p-4">
              <h3 className="text-sm font-medium mb-3">
                Avg Whale Score: Winners vs Losers
              </h3>
              <div className="flex gap-8 text-sm">
                <div>
                  <span className="text-muted-foreground">Winners: </span>
                  <span className="text-success font-mono">
                    {summary.avg_score_winners?.toFixed(3) ?? "N/A"}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground">Losers: </span>
                  <span className="text-destructive font-mono">
                    {summary.avg_score_losers?.toFixed(3) ?? "N/A"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-8 text-muted-foreground">
          <p>
            No paper trading data yet. Enable paper trading in config.toml and
            run the monitor.
          </p>
        </div>
      )}

      {/* Open Positions */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">Open Positions</h3>
        {openPositions && openPositions.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                  <th className="py-2 px-2">Market</th>
                  <th className="py-2 px-2">Outcome</th>
                  <th className="py-2 px-2 text-right">Entry</th>
                  <th className="py-2 px-2 text-right">Current</th>
                  <th className="py-2 px-2 text-right">Unrlzd PnL</th>
                  <th className="py-2 px-2 text-right">Cost</th>
                  <th className="py-2 px-2 text-right">Score</th>
                  <th className="py-2 px-2">Whale</th>
                  <th className="py-2 px-2">Opened</th>
                </tr>
              </thead>
              <tbody>
                {openPositions.map((p) => {
                  const currentPrice = getCurrentPrice(p);
                  const unrealizedPnl = getUnrealizedPnl(p);
                  return (
                    <tr
                      key={p.id}
                      className="border-b border-border/50 hover:bg-muted/50"
                    >
                      <td className="py-2 px-2 truncate max-w-40">
                        <Link
                          href={`/markets/${p.market_slug}`}
                          className="hover:text-accent"
                        >
                          {p.market_title || p.market_slug}
                        </Link>
                      </td>
                      <td className="py-2 px-2">{p.outcome}</td>
                      <td className="py-2 px-2 text-right font-mono">
                        ${p.entry_price.toFixed(3)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono">
                        {currentPrice !== null ? (
                          <span
                            className={
                              currentPrice > p.entry_price
                                ? "text-success"
                                : currentPrice < p.entry_price
                                  ? "text-destructive"
                                  : ""
                            }
                          >
                            ${currentPrice.toFixed(3)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">--</span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-right font-mono">
                        {unrealizedPnl !== null ? (
                          <span
                            className={
                              unrealizedPnl >= 0
                                ? "text-success"
                                : "text-destructive"
                            }
                          >
                            {unrealizedPnl >= 0 ? "+" : ""}
                            {formatUsd(unrealizedPnl)}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">--</span>
                        )}
                      </td>
                      <td className="py-2 px-2 text-right font-mono">
                        {formatUsd(p.cost_basis)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono">
                        {p.whale_score.toFixed(2)}
                      </td>
                      <td className="py-2 px-2 font-mono text-xs">
                        <Link
                          href={`/wallets/${p.whale_wallet}`}
                          className="hover:text-accent"
                        >
                          {truncateWallet(p.whale_wallet)}
                        </Link>
                      </td>
                      <td className="py-2 px-2 text-xs text-muted-foreground">
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-4">
            No open positions
          </p>
        )}
      </div>

      {/* Closed Positions */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">Closed Positions</h3>
        {closedAll.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                  <th className="py-2 px-2">Market</th>
                  <th className="py-2 px-2">Outcome</th>
                  <th className="py-2 px-2 text-right">Entry</th>
                  <th className="py-2 px-2 text-right">Exit</th>
                  <th className="py-2 px-2 text-right">PnL</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 px-2 text-right">Score</th>
                </tr>
              </thead>
              <tbody>
                {closedAll.map((p) => (
                  <tr
                    key={p.id}
                    className="border-b border-border/50 hover:bg-muted/50"
                  >
                    <td className="py-2 px-2 truncate max-w-40">
                      {p.market_title || p.market_slug}
                    </td>
                    <td className="py-2 px-2">{p.outcome}</td>
                    <td className="py-2 px-2 text-right font-mono">
                      ${p.entry_price.toFixed(3)}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      ${p.exit_price?.toFixed(3) ?? "-"}
                    </td>
                    <td
                      className={`py-2 px-2 text-right font-mono ${
                        (p.pnl ?? 0) >= 0
                          ? "text-success"
                          : "text-destructive"
                      }`}
                    >
                      {p.pnl !== null
                        ? `${p.pnl >= 0 ? "+" : ""}${formatUsd(p.pnl)}`
                        : "-"}
                    </td>
                    <td className="py-2 px-2">
                      <span
                        className={`inline-flex px-1.5 py-0.5 rounded text-xs font-medium ${
                          p.status === "won"
                            ? "bg-success/20 text-success"
                            : "bg-destructive/20 text-destructive"
                        }`}
                      >
                        {p.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      {p.whale_score.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground text-center py-4">
            No closed positions yet
          </p>
        )}
      </div>
    </div>
  );
}
