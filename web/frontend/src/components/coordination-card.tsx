"use client";

import Link from "next/link";
import type { CoordinatedEntry } from "@/lib/types";
import { useState } from "react";

function truncateWallet(address: string): string {
  if (address.length > 12) {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  }
  return address;
}

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

interface CoordinationCardProps {
  entry: CoordinatedEntry;
}

export default function CoordinationCard({ entry }: CoordinationCardProps) {
  const [expanded, setExpanded] = useState(false);

  const confidenceColor =
    entry.confidence >= 0.7
      ? "text-destructive"
      : entry.confidence >= 0.5
        ? "text-warning"
        : "text-accent";

  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-medium text-sm truncate">
            <Link
              href={`/markets/${entry.market_slug}`}
              className="hover:text-accent"
            >
              {entry.market_title || entry.market_slug}
            </Link>
          </p>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span>Outcome: {entry.outcome}</span>
            <span>Avg price: ${entry.avg_price.toFixed(3)}</span>
            <span>{formatUsd(entry.total_usdc)} total</span>
          </div>
        </div>
        <div className="text-right">
          <p className={`text-lg font-bold ${confidenceColor}`}>
            {(entry.confidence * 100).toFixed(0)}%
          </p>
          <p className="text-xs text-muted-foreground">confidence</p>
        </div>
      </div>

      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground">
        <span>{entry.wallets.length} wallets</span>
        <span>{entry.fresh_wallet_count} fresh</span>
        <span>{entry.trade_count} trades</span>
        <span>
          {Math.round(entry.time_spread_seconds / 60)}min spread
        </span>
      </div>

      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-2 text-xs text-accent hover:underline"
      >
        {expanded ? "Hide wallets" : "Show wallets"}
      </button>

      {expanded && (
        <div className="mt-2 space-y-1">
          {entry.wallets.map((w) => (
            <Link
              key={w}
              href={`/wallets/${w}`}
              className="block text-xs font-mono text-muted-foreground hover:text-accent"
            >
              {truncateWallet(w)}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
