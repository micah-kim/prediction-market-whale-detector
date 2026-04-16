import Link from "next/link";
import type { Trade } from "@/lib/types";

function truncateWallet(address: string): string {
  if (address.length > 12) {
    return `${address.slice(0, 6)}...${address.slice(-4)}`;
  }
  return address;
}

function formatUsd(value: number): string {
  return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

interface TradeTableProps {
  trades: Trade[];
  showMarket?: boolean;
}

export default function TradeTable({
  trades,
  showMarket = false,
}: TradeTableProps) {
  if (trades.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-4 text-center">
        No trades found
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground uppercase tracking-wide">
            <th className="py-2 px-3">Time</th>
            {showMarket && <th className="py-2 px-3">Market</th>}
            <th className="py-2 px-3">Side</th>
            <th className="py-2 px-3">Outcome</th>
            <th className="py-2 px-3 text-right">Price</th>
            <th className="py-2 px-3 text-right">USDC</th>
            <th className="py-2 px-3">Wallet</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr
              key={t.transaction_hash}
              className="border-b border-border/50 hover:bg-muted/50"
            >
              <td className="py-2 px-3 text-xs text-muted-foreground whitespace-nowrap">
                {new Date(t.timestamp * 1000).toLocaleString()}
              </td>
              {showMarket && (
                <td className="py-2 px-3 truncate max-w-48">
                  <Link
                    href={`/markets/${t.slug}`}
                    className="hover:text-accent"
                  >
                    {t.title || t.slug}
                  </Link>
                </td>
              )}
              <td className="py-2 px-3">
                <span
                  className={
                    t.side === "BUY" ? "text-success" : "text-destructive"
                  }
                >
                  {t.side}
                </span>
              </td>
              <td className="py-2 px-3">{t.outcome}</td>
              <td className="py-2 px-3 text-right font-mono">
                ${t.price.toFixed(3)}
              </td>
              <td className="py-2 px-3 text-right font-mono">
                {formatUsd(t.usdc_value)}
              </td>
              <td className="py-2 px-3 font-mono text-xs">
                <Link
                  href={`/wallets/${t.proxy_wallet}`}
                  className="hover:text-accent"
                >
                  {t.pseudonym || truncateWallet(t.proxy_wallet)}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
