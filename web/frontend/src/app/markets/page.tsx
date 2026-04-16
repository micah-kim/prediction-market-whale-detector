"use client";

import Link from "next/link";
import { usePolling } from "@/hooks/use-polling";
import type { TopMarket } from "@/lib/types";

function formatUsd(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

export default function MarketsPage() {
  const { data: markets, loading } = usePolling<TopMarket[]>(
    "/api/stats/top-markets?limit=25",
    30000,
  );

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Markets</h2>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading...</p>
      ) : !markets || markets.length === 0 ? (
        <p className="text-muted-foreground text-sm text-center py-12">
          No markets tracked yet
        </p>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                <th className="py-2 px-3">Market</th>
                <th className="py-2 px-3 text-right">Trades</th>
                <th className="py-2 px-3 text-right">Wallets</th>
                <th className="py-2 px-3 text-right">Volume</th>
              </tr>
            </thead>
            <tbody>
              {markets.map((m) => (
                <tr
                  key={m.condition_id}
                  className="border-b border-border/50 hover:bg-muted/50"
                >
                  <td className="py-2 px-3">
                    <Link
                      href={`/markets/${encodeURIComponent(m.market_name)}`}
                      className="hover:text-accent"
                    >
                      {m.market_name}
                    </Link>
                  </td>
                  <td className="py-2 px-3 text-right font-mono">
                    {m.trade_count}
                  </td>
                  <td className="py-2 px-3 text-right font-mono">
                    {m.unique_wallets}
                  </td>
                  <td className="py-2 px-3 text-right font-mono">
                    {formatUsd(m.total_volume)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
