"use client";

import { usePolling } from "@/hooks/use-polling";

interface ConfigData {
  db_path: string;
  poll_interval_seconds: number;
  log_level: string;
  thresholds: Record<string, number>;
  scoring: Record<string, number>;
  alerting: { sinks: string[]; [key: string]: unknown };
  markets: {
    watch_slugs: string[];
    exclude_slug_patterns: string[];
  };
}

function ConfigSection({
  title,
  entries,
}: {
  title: string;
  entries: [string, unknown][];
}) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <h3 className="text-sm font-medium mb-3">{title}</h3>
      <div className="space-y-1">
        {entries.map(([key, value]) => (
          <div key={key} className="flex justify-between text-sm">
            <span className="text-muted-foreground">{key}</span>
            <span className="font-mono">
              {typeof value === "object"
                ? JSON.stringify(value)
                : String(value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data: config, loading } = usePolling<ConfigData>("/api/config", 60000);

  if (loading) {
    return <p className="text-muted-foreground text-sm">Loading config...</p>;
  }

  if (!config) {
    return <p className="text-muted-foreground">Could not load configuration</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">Settings</h2>
      <p className="text-sm text-muted-foreground">
        Read-only view of effective configuration. Edit config.toml or use
        environment variables to change settings.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ConfigSection
          title="General"
          entries={[
            ["db_path", config.db_path],
            ["poll_interval_seconds", config.poll_interval_seconds],
            ["log_level", config.log_level],
          ]}
        />

        <ConfigSection
          title="Thresholds"
          entries={Object.entries(config.thresholds)}
        />

        <ConfigSection
          title="Scoring Weights"
          entries={Object.entries(config.scoring)}
        />

        <ConfigSection
          title="Alerting"
          entries={Object.entries(config.alerting)}
        />

        <ConfigSection
          title="Market Filter"
          entries={Object.entries(config.markets)}
        />
      </div>
    </div>
  );
}
