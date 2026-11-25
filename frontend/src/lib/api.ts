export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type Health = {
  status: string;
  time: string;
  database: string;
  instruments: number;
  keys_configured: Record<string, boolean>;
  disclaimer: string;
};

export type StockRow = {
  key: string;
  symbol: string;
  name: string | null;
  isin: string | null;
  exchanges: string[];
  bse_symbol: string | null;
  series: string | null;
  close: number | null;
  prev_close: number | null;
  change_pct: number | null;
  volume: number | null;
  turnover: number | null;
  price_date: string | null;
  price_source: string | null;
};

export type StocksResponse = { as_of: Record<string, string | null>; count: number; rows: StockRow[] };

export type IndexTile = {
  label: string;
  key: string;
  close: number | null;
  change: number | null;
  change_pct: number | null;
  as_of: string | null;
  source: string | null;
};

export type Tick = { ltp: number; cp: number | null; ltt: string | null };

export type MarketStatus = {
  time: string;
  market_open_by_clock: boolean;
  segment_status: Record<string, string>;
  live: { state: string; message: string | null; last_tick_at: string | null; source: string };
  upstox_keys_set: boolean;
  jobs: Record<string, { ok: boolean; detail: string; at: string }>;
};

/** A row with live data merged in. */
export type LiveRow = StockRow & {
  price: number | null;
  pct: number | null;
  live: boolean;
  priceAsOf: string | null; // ISO date or datetime
  priceSource: string | null;
};

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export function pct(price: number | null, prev: number | null): number | null {
  if (price == null || !prev) return null;
  return Math.round(((price - prev) / prev) * 10000) / 100;
}

export function mergeLive(row: StockRow, tick?: Tick): LiveRow {
  if (tick) {
    return {
      ...row,
      price: tick.ltp,
      pct: pct(tick.ltp, tick.cp ?? row.close),
      live: true,
      priceAsOf: tick.ltt,
      priceSource: "Upstox live feed",
    };
  }
  return {
    ...row,
    price: row.close,
    pct: row.change_pct,
    live: false,
    priceAsOf: row.price_date,
    priceSource: row.price_source,
  };
}

const NA = "not available";
const inr = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const int = new Intl.NumberFormat("en-IN");

export const fmtPrice = (v: number | null) => (v == null ? NA : inr.format(v));
export const fmtInt = (v: number | null) => (v == null ? NA : int.format(v));
export const fmtCr = (v: number | null) => (v == null ? NA : inr.format(v / 1e7));
export const fmtPct = (v: number | null) => (v == null ? NA : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`);
export const pctColor = (v: number | null) =>
  v == null ? "text-slate-400" : v > 0 ? "text-green-700" : v < 0 ? "text-red-700" : "text-slate-600";

export function fmtAsOf(v: string | null): string {
  if (!v) return NA;
  if (v.length === 10) {
    return `close of ${new Date(v + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}`;
  }
  return new Date(v).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
