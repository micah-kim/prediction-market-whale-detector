import type { ImpactLevel } from "@/lib/types";

const COLORS: Record<ImpactLevel, string> = {
  high: "bg-destructive/20 text-destructive border-destructive/30",
  medium: "bg-warning/20 text-warning border-warning/30",
  low: "bg-accent/20 text-accent border-accent/30",
};

interface ScoreBadgeProps {
  impact: ImpactLevel;
  score?: number;
}

export default function ScoreBadge({ impact, score }: ScoreBadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ${COLORS[impact] || COLORS.low}`}
    >
      {impact.toUpperCase()}
      {score !== undefined && (
        <span className="ml-1 opacity-75">{score.toFixed(2)}</span>
      )}
    </span>
  );
}
