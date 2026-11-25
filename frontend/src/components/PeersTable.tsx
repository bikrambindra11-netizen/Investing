import Link from "next/link";
import type { Peer } from "@/lib/types";
import { fmtCr, fmtPct, fmtPrice, pctColor } from "@/lib/api";
import { fmtDate, num } from "./ui";

export function PeersTable({ peers, highlight }: { peers: Peer[]; highlight?: string }) {
  const anyRatios = peers.some((p) => p.pe != null || p.pb != null || p.roe != null);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="text-left text-xs text-slate-500">
          <tr>
            <th className="py-1 pr-2 font-medium">Company</th>
            <th className="py-1 pr-2 text-right font-medium">Price (₹)</th>
            <th className="py-1 pr-2 text-right font-medium">Change</th>
            <th className="py-1 pr-2 text-right font-medium">Traded (₹ Cr)</th>
            <th className="py-1 pr-2 text-right font-medium">P/E</th>
            <th className="py-1 pr-2 text-right font-medium">P/B</th>
            <th className="py-1 pr-2 text-right font-medium">EV/EBITDA</th>
            <th className="py-1 pr-2 text-right font-medium">ROE</th>
            <th className="py-1 pr-2 text-right font-medium">ROCE</th>
          </tr>
        </thead>
        <tbody>
          {peers.map((p) => (
            <tr key={p.isin} className={`border-t ${p.isin === highlight ? "bg-amber-50" : ""}`}>
              <td className="max-w-[14rem] py-1.5 pr-2">
                <Link href={`/stock/${p.isin}`} className="font-medium hover:underline">{p.symbol}</Link>
                {p.isin === highlight && <span className="ml-1 text-[10px] text-amber-700">this stock</span>}
                <div className="truncate text-xs text-slate-500">{p.name}</div>
              </td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{fmtPrice(p.close)}</td>
              <td className={`py-1.5 pr-2 text-right tabular-nums ${pctColor(p.change_pct)}`}>{fmtPct(p.change_pct)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{fmtCr(p.turnover)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{num(p.pe)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{num(p.pb)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{num(p.ev_ebitda)}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{p.roe == null ? "not available" : `${p.roe}%`}</td>
              <td className="py-1.5 pr-2 text-right tabular-nums">{p.roce == null ? "not available" : `${p.roce}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-slate-400">
        Prices: exchange close of {fmtDate(peers.find((p) => p.price_date)?.price_date)}. Ratios: Upstox fundamentals
        {anyRatios ? "" : " (shown after you log in with Upstox)"}.
      </p>
    </div>
  );
}
