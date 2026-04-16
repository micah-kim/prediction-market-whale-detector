"use client";

import { use } from "react";
import StatCard from "@/components/stat-card";
import { usePolling } from "@/hooks/use-polling";
import type { WalletProfile } from "@/lib/types";

function formatUsd(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
  return `$${value.toFixed(0)}`;
}

function truncateWallet(address: string): string {
  if (address.length > 16)
    return `${address.slice(0, 8)}...${address.slice(-6)}`;
  return address;
}

export default function WalletProfilePage({
  params,
}: {
  params: Promise<{ address: string }>;
}) {
  const { address } = use(params);
  const { data: profile, loading } = usePolling<WalletProfile>(
    `/api/wallets/${address}`,
    30000,
  );

  if (loading) {
    return (
      <p className="text-muted-foreground text-sm">Loading wallet profile...</p>
    );
  }

  if (!profile) {
    return <p className="text-muted-foreground">Wallet not found</p>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold">
          {profile.pseudonym || truncateWallet(profile.address)}
        </h2>
        <p className="text-xs text-muted-foreground font-mono mt-1">
          {profile.address}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard title="Total Trades" value={profile.total_trades} />
        <StatCard title="Unique Markets" value={profile.unique_markets} />
        <StatCard
          title="Total Volume"
          value={formatUsd(profile.total_usdc_volume)}
        />
        <StatCard
          title="Buy / Sell"
          value={`${profile.buy_count} / ${profile.sell_count}`}
        />
      </div>

      <div className="bg-card border border-border rounded-lg p-4">
        <h3 className="text-sm font-medium mb-3">Activity</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">First Seen</p>
            <p>
              {profile.first_seen
                ? new Date(profile.first_seen).toLocaleDateString()
                : "N/A"}
            </p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Last Seen</p>
            <p>
              {profile.last_seen
                ? new Date(profile.last_seen).toLocaleDateString()
                : "N/A"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
