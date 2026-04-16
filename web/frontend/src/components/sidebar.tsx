"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: "grid" },
  { href: "/live", label: "Live Feed", icon: "activity" },
  { href: "/alerts", label: "Alerts", icon: "bell" },
  { href: "/coordination", label: "Coordination", icon: "users" },
  { href: "/markets", label: "Markets", icon: "bar-chart" },
  { href: "/paper-trading", label: "Paper Trading", icon: "trending-up" },
  { href: "/settings", label: "Settings", icon: "settings" },
];

const ICONS: Record<string, string> = {
  grid: "\u25A6",
  activity: "\u2261",
  bell: "\u266A",
  users: "\u2687",
  "bar-chart": "\u2593",
  "trending-up": "\u2197",
  settings: "\u2699",
};

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-56 flex-shrink-0 bg-card border-r border-border flex flex-col">
      <div className="p-4 border-b border-border">
        <h1 className="text-lg font-bold tracking-tight">Whale Detector</h1>
        <p className="text-xs text-muted-foreground mt-0.5">v0.1.0</p>
      </div>
      <nav className="flex-1 p-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors ${
                active
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <span className="text-base w-5 text-center">
                {ICONS[item.icon]}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
