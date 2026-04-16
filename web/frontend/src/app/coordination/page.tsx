"use client";

import CoordinationCard from "@/components/coordination-card";
import { usePolling } from "@/hooks/use-polling";
import type { CoordinatedEntry } from "@/lib/types";

export default function CoordinationPage() {
  const { data: entries, loading } = usePolling<CoordinatedEntry[]>(
    "/api/coordination",
    30000,
  );

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Coordination Patterns</h2>
      <p className="text-sm text-muted-foreground">
        Detected bursts of fresh wallets buying minority-side outcomes in the
        same market within a tight time window.
      </p>

      {loading ? (
        <p className="text-muted-foreground text-sm">Scanning...</p>
      ) : !entries || entries.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg">No coordination patterns detected</p>
          <p className="text-sm mt-1">
            Patterns appear when 3+ fresh wallets buy minority outcomes in the
            same market within 1 hour
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <CoordinationCard key={entry.condition_id} entry={entry} />
          ))}
        </div>
      )}
    </div>
  );
}
