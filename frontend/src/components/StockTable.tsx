"use client";

import { useMemo, useState } from "react";
import { fmtAsOf, fmtCr, fmtInt, fmtPct, fmtPrice, pctColor, type LiveRow } from "@/lib/api";

type SortKey = "symbol" | "price" | "pct" | "volume" | "turnover";
type ExFilter = "all" | "NSE" | "BSE_ONLY";
const PAGE = 50;

const COLS: { key: SortKey; label: string; right?: boolean }[] = [
  { key: "symbol", label: "Stock" },
  { key: "price", label: "Price (₹)", right: true },
  { key: "pct", label: "Change", right: true },
  { key: "volume", label: "Volume (last session)", right: true },
  { key: "turnover", label: "Traded ₹ Cr (last session)", right: true },
];

export function StockTable({ rows }: { rows: LiveRow[] }) {
  const [q, setQ] = useState("");
  const [ex, setEx] = useState<ExFilter>("all");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "turnover", desc: true });
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    let out = rows;
    if (ex === "NSE") out = out.filter((r) => r.exchanges.includes("NSE"));
    if (ex === "BSE_ONLY") out = out.filter((r) => !r.exchanges.includes("NSE"));
    if (term) {
      out = out.filter(
        (r) =>
          r.symbol.toLowerCase().includes(term) ||
          (r.name ?? "").toLowerCase().includes(term) ||
          (r.bse_symbol ?? "").toLowerCase().includes(term) ||
          (r.isin ?? "").toLowerCase() === term,
      );
    }
    const dir = sort.desc ? -1 : 1;
    return [...out].sort((a, b) => {
      if (sort.key === "symbol") return a.symbol.localeCompare(b.symbol) * dir;
      const av = a[sort.key], bv = b[sort.key];
      if (av == null && bv == null) return 0;
      if (av == null) return 1; // "not available" always last
      if (bv == null) return -1;
      return (av - bv) * dir;
    });
  }, [rows, q, ex, sort]);

  const pages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const current = Math.min(page, pages - 1);
  const shown = filtered.slice(current * PAGE, current * PAGE + PAGE);

  const clickSort = (key: SortKey) => {
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== "symbol" }));
    setPage(0);
  };

  return (
    <div className="rounded border bg-white">
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(0); }}
          placeholder="Search by symbol, company name or ISIN"
          className="min-w-0 flex-1 rounded border px-3 py-1.5 text-sm"
        />
        <select
          value={ex}
          onChange={(e) => { setEx(e.target.value as ExFilter); setPage(0); }}
          className="rounded border px-2 py-1.5 text-sm"
          aria-label="Exchange"
        >
          <option value="all">NSE + BSE</option>
          <option value="NSE">Listed on NSE</option>
          <option value="BSE_ONLY">BSE only</option>
        </select>
        <span className="text-xs text-slate-500">{fmtInt(filtered.length)} stocks</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500">
            <tr>
              {COLS.map((c) => (
                <th key={c.key} className={`px-3 py-2 font-medium ${c.right ? "text-right" : "text-left"}`}>
                  <button onClick={() => clickSort(c.key)} className="hover:text-slate-900">
                    {c.label}
                    {sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                  </button>
                </th>
              ))}
              <th className="px-3 py-2 text-left font-medium">As of</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.key} className="border-t hover:bg-slate-50">
                <td className="max-w-[16rem] px-3 py-1.5">
                  <div className="font-medium">
                    {r.symbol}
                    <span className="ml-1 text-[10px] text-slate-400">{r.exchanges.join(" · ")}</span>
                  </div>
                  <div className="truncate text-xs text-slate-500">{r.name}</div>
                </td>
                <td className="px-3 py-1.5 text-right tabular-nums">{fmtPrice(r.price)}</td>
                <td className={`px-3 py-1.5 text-right tabular-nums ${pctColor(r.pct)}`}>{fmtPct(r.pct)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{fmtInt(r.volume)}</td>
                <td className="px-3 py-1.5 text-right tabular-nums">{fmtCr(r.turnover)}</td>
                <td className="whitespace-nowrap px-3 py-1.5 text-xs text-slate-500" title={`Source: ${r.priceSource ?? "not available"}`}>
                  {r.live && <span className="mr-1 inline-block h-2 w-2 rounded-full bg-green-500" aria-label="live" />}
                  {fmtAsOf(r.priceAsOf)}
                </td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-slate-400">No stocks match.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between border-t p-3 text-sm">
        <button disabled={current === 0} onClick={() => setPage(current - 1)} className="rounded border px-3 py-1 disabled:opacity-40">Previous</button>
        <span className="text-slate-500">Page {current + 1} of {pages}</span>
        <button disabled={current >= pages - 1} onClick={() => setPage(current + 1)} className="rounded border px-3 py-1 disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}
