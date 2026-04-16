import Link from "next/link";
import type { AlertRecord, ImpactLevel } from "@/lib/types";
import ScoreBadge from "./score-badge";

function truncateWallet(address: string): string {
  if (address.length > 12) {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  }
  return address;
}

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

interface AlertCardProps {
  alert: AlertRecord;
}

export default function AlertCard({ alert }: AlertCardProps) {
  const reasons: string[] = JSON.parse(alert.reasons_json || "[]");

  return (
    <div className="bg-card border border-border rounded-lg p-4 transition-all hover:border-muted-foreground/30">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <ScoreBadge
              impact={alert.impact as ImpactLevel}
              score={alert.composite_score}
            />
            <span className="text-xs text-muted-foreground">
              {new Date(alert.created_at).toLocaleString()}
            </span>
          </div>
          <p className="font-medium text-sm truncate">
            {alert.title || "Unknown Market"}
          </p>
          <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
            <span>
              {alert.outcome} ({alert.side})
            </span>
            <span className="font-mono">{formatUsd(alert.usdc_value)}</span>
            <Link
              href={`/wallets/${alert.proxy_wallet}`}
              className="font-mono hover:text-accent"
            >
              {alert.pseudonym || truncateWallet(alert.proxy_wallet)}
            </Link>
          </div>
        </div>
      </div>
      {reasons.length > 0 && (
        <div className="mt-2 text-xs text-muted-foreground space-y-0.5">
          {reasons.map((r, i) => (
            <p key={i}>- {r}</p>
          ))}
        </div>
      )}
    </div>
  );
}
