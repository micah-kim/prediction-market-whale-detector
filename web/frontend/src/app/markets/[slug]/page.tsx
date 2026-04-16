"use client";

import { use } from "react";
import TradeTable from "@/components/trade-table";
import { usePolling } from "@/hooks/use-polling";
import type { Trade } from "@/lib/types";

export default function MarketDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const decoded = decodeURIComponent(slug);
  const { data: trades, loading } = usePolling<Trade[]>(
    `/api/markets/${encodeURIComponent(decoded)}?limit=50`,
    15000,
  );

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">{decoded}</h2>

      {loading ? (
        <p className="text-muted-foreground text-sm">Loading trades...</p>
      ) : (
        <div className="bg-card border border-border rounded-lg p-4">
          <TradeTable trades={trades ?? []} />
        </div>
      )}
    </div>
  );
}
