import Link from "next/link";
import { fmtCr, fmtPct, fmtPrice, pctColor, type LiveRow } from "@/lib/api";

function List({ title, rows }: { title: string; rows: LiveRow[] }) {
  return (
    <div className="rounded border bg-white p-3">
      <h3 className="mb-2 text-sm font-semibold">{title}</h3>
      {rows.length === 0 && <p className="text-sm text-slate-400">not available</p>}
      <ol className="space-y-1 text-sm">
        {rows.map((r) => (
          <li key={r.key} className="flex items-baseline justify-between gap-2">
            <span className="truncate">
              <Link href={`/stock/${r.isin}`} className="font-medium hover:underline">{r.symbol}</Link>{" "}
              <span className="text-xs text-slate-400">₹{fmtCr(r.turnover)} Cr</span>
            </span>
            <span className="shrink-0 tabular-nums">
              {fmtPrice(r.price)} <span className={pctColor(r.pct)}>{fmtPct(r.pct)}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Top gainers and losers, among stocks with at least ₹1 crore traded (skips illiquid names). */
export function Movers({ rows }: { rows: LiveRow[] }) {
  const liquid = rows.filter((r) => r.pct != null && (r.turnover ?? 0) >= 1e7);
  const sorted = [...liquid].sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));
  return (
    <div>
      <div className="grid gap-2 md:grid-cols-2">
        <List title="Top gainers" rows={sorted.slice(0, 5)} />
        <List title="Top losers" rows={sorted.slice(-5).reverse()} />
      </div>
      <p className="mt-1 text-[11px] text-slate-400">
        Among stocks with at least ₹1 crore traded in the last session (turnover from the exchange close file).
      </p>
    </div>
  );
}
