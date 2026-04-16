"use client";

import { useState } from "react";
import Link from "next/link";
import AlertCard from "@/components/alert-card";
import TradeTable from "@/components/trade-table";
import { usePolling } from "@/hooks/use-polling";
import type { AlertRecord, ImpactLevel, Trade } from "@/lib/types";

export default function LiveFeedPage() {
  const { data: trades, loading: tradesLoading } = usePolling<Trade[]>(
    "/api/trades/live?limit=30",
    5000,
  );
  const { data: alerts, loading: alertsLoading } = usePolling<AlertRecord[]>(
    "/api/alerts/live",
    5000,
  );
  const [tab, setTab] = useState<"trades" | "alerts">("trades");

  const alertCount = alerts?.length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Live Feed</h2>
        <p className="text-xs text-muted-foreground">Auto-refreshes every 5s</p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-1 bg-muted rounded-lg p-1 w-fit">
        <button
          onClick={() => setTab("trades")}
          className={`px-3 py-1.5 rounded text-sm transition-colors ${
            tab === "trades"
              ? "bg-card text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Recent Trades
        </button>
        <button
          onClick={() => setTab("alerts")}
          className={`px-3 py-1.5 rounded text-sm transition-colors ${
            tab === "alerts"
              ? "bg-card text-foreground font-medium"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          Alerts{alertCount > 0 && ` (${alertCount})`}
        </button>
      </div>

      {tab === "trades" ? (
        tradesLoading ? (
          <p className="text-muted-foreground text-sm">Loading trades...</p>
        ) : !trades || trades.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <p className="text-lg">No trades yet</p>
            <p className="text-sm mt-1">
              Trades will appear here as the monitor collects data
            </p>
          </div>
        ) : (
          <div className="bg-card border border-border rounded-lg p-4">
            <TradeTable trades={trades} showMarket />
          </div>
        )
      ) : alertsLoading ? (
        <p className="text-muted-foreground text-sm">Loading alerts...</p>
      ) : !alerts || alerts.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg">No alerts yet</p>
          <p className="text-sm mt-1">
            Alerts appear when a trade scores above the threshold (default
            0.50)
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert, i) => (
            <AlertCard key={`${alert.created_at}-${i}`} alert={alert} />
          ))}
        </div>
      )}
    </div>
  );
}
