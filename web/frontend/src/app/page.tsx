"use client";

import Link from "next/link";
import StatCard from "@/components/stat-card";
import VolumeChart from "@/components/volume-chart";
import { usePolling } from "@/hooks/use-polling";
import type { GlobalStats, TopMarket, TopWallet } from "@/lib/types";

function formatUsd(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function truncateWallet(address: string): string {
  if (address.length > 12)
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  return address;
}

export default function DashboardPage() {
  const { data: stats, loading: statsLoading } =
    usePolling<GlobalStats>("/api/stats", 10000);
  const { data: markets } = usePolling<TopMarket[]>(
    "/api/stats/top-markets?limit=5",
    30000,
  );
  const { data: wallets } = usePolling<TopWallet[]>(
    "/api/stats/top-wallets?limit=5",
    30000,
  );

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Loading dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">Dashboard</h2>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <StatCard
          title="Total Trades"
          value={stats?.total_trades?.toLocaleString() ?? "0"}
        />
        <StatCard
          title="Unique Wallets"
          value={stats?.unique_wallets?.toLocaleString() ?? "0"}
        />
        <StatCard
          title="Active Markets"
          value={stats?.unique_markets?.toLocaleString() ?? "0"}
        />
        <StatCard
          title="Total Volume"
          value={stats ? formatUsd(stats.total_volume) : "$0"}
        />
        <StatCard
          title="Alerts"
          value={stats?.alert_count?.toLocaleString() ?? "0"}
        />
      </div>

      {/* Volume Chart placeholder */}
      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">Volume Overview</h3>
        <VolumeChart data={[]} />
      </div>

      {/* Top Markets + Top Wallets */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Markets */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Top Markets by Volume</h3>
          {markets && markets.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                  <th className="py-2 px-2">Market</th>
                  <th className="py-2 px-2 text-right">Trades</th>
                  <th className="py-2 px-2 text-right">Volume</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m) => (
                  <tr
                    key={m.condition_id}
                    className="border-b border-border/50"
                  >
                    <td className="py-2 px-2 truncate max-w-48">
                      {m.market_name}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      {m.trade_count}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      {formatUsd(m.total_volume)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">No market data</p>
          )}
        </div>

        {/* Top Wallets */}
        <div className="bg-card border border-border rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Top Wallets by Volume</h3>
          {wallets && wallets.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                  <th className="py-2 px-2">Wallet</th>
                  <th className="py-2 px-2 text-right">Trades</th>
                  <th className="py-2 px-2 text-right">Volume</th>
                </tr>
              </thead>
              <tbody>
                {wallets.map((w) => (
                  <tr
                    key={w.proxy_wallet}
                    className="border-b border-border/50"
                  >
                    <td className="py-2 px-2 font-mono text-xs">
                      <Link
                        href={`/wallets/${w.proxy_wallet}`}
                        className="hover:text-accent"
                      >
                        {w.pseudonym || truncateWallet(w.proxy_wallet)}
                      </Link>
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      {w.trade_count}
                    </td>
                    <td className="py-2 px-2 text-right font-mono">
                      {formatUsd(w.total_volume)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">No wallet data</p>
          )}
        </div>
      </div>
    </div>
  );
}
