"use client";

import Link from "next/link";
import ScoreBadge from "@/components/score-badge";
import { usePolling } from "@/hooks/use-polling";
import type { AlertRecord, ImpactLevel } from "@/lib/types";

function truncateWallet(address: string): string {
  if (address.length > 12)
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  return address;
}

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

export default function AlertsPage() {
  const { data: alerts, loading } = usePolling<AlertRecord[]>(
    "/api/alerts?limit=50",
    15000,
  );

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Alerts History</h2>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading...</p>
      ) : !alerts || alerts.length === 0 ? (
        <p className="text-muted-foreground text-sm text-center py-12">
          No alerts recorded yet
        </p>
      ) : (
        <div className="bg-card border border-border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
                <th className="py-2 px-3">Time</th>
                <th className="py-2 px-3">Impact</th>
                <th className="py-2 px-3">Market</th>
                <th className="py-2 px-3">Outcome</th>
                <th className="py-2 px-3 text-right">USDC</th>
                <th className="py-2 px-3">Wallet</th>
              </tr>
            </thead>
            <tbody>
              {alerts.map((a, i) => (
                <tr
                  key={`${a.created_at}-${i}`}
                  className="border-b border-border/50 hover:bg-muted/50"
                >
                  <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 px-3">
                    <ScoreBadge
                      impact={a.impact as ImpactLevel}
                      score={a.composite_score}
                    />
                  </td>
                  <td className="py-2 px-3 truncate max-w-48">
                    <Link
                      href={`/markets/${a.slug}`}
                      className="hover:text-accent"
                    >
                      {a.title || a.slug || "Unknown"}
                    </Link>
                  </td>
                  <td className="py-2 px-3">
                    {a.outcome} ({a.side})
                  </td>
                  <td className="py-2 px-3 text-right font-mono">
                    {formatUsd(a.usdc_value)}
                  </td>
                  <td className="py-2 px-3 font-mono text-xs">
                    <Link
                      href={`/wallets/${a.proxy_wallet}`}
                      className="hover:text-accent"
                    >
                      {a.pseudonym || truncateWallet(a.proxy_wallet)}
                    </Link>
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
