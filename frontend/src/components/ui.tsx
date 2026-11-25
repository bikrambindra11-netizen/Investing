import type { ReactNode } from "react";

export function Section({ title, subtitle, children, id }: { title: string; subtitle?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="rounded border bg-white p-4">
      <h2 className="text-base font-semibold">{title}</h2>
      {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

export function Source({ source, asOf }: { source?: string | null; asOf?: string | null }) {
  if (!source && !asOf) return null;
  return (
    <p className="mt-2 text-[11px] text-slate-400">
      Source: {source ?? "not available"}
      {asOf ? ` · as of ${fmtDate(asOf)}` : ""}
    </p>
  );
}

export function fmtDate(v: string | null | undefined): string {
  if (!v) return "not available";
  const d = new Date(v.length === 10 ? v + "T00:00:00" : v);
  if (isNaN(d.getTime())) return v;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

const VERDICT: Record<string, string> = {
  tailwind: "bg-green-100 text-green-800",
  headwind: "bg-red-100 text-red-800",
  neutral: "bg-slate-100 text-slate-700",
  pass: "bg-green-100 text-green-800",
  fail: "bg-red-100 text-red-800",
  partial: "bg-amber-100 text-amber-800",
  skipped: "bg-slate-100 text-slate-600",
  not_available: "bg-slate-100 text-slate-500",
  "not available": "bg-slate-100 text-slate-500",
  positive: "bg-green-100 text-green-800",
  negative: "bg-red-100 text-red-800",
  cheap: "bg-green-100 text-green-800",
  fair: "bg-slate-100 text-slate-700",
  expensive: "bg-red-100 text-red-800",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded px-1.5 py-0.5 text-[11px] font-medium ${VERDICT[value] ?? "bg-slate-100 text-slate-600"}`}>
      {label ?? value.replace("_", " ")}
    </span>
  );
}

export function Sparkline({ points, width = 90, height = 24 }: { points: [string, number][]; width?: number; height?: number }) {
  if (!points || points.length < 2) return <span className="text-[11px] text-slate-400">—</span>;
  const vals = points.map((p) => p[1]);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const d = vals
    .map((v, i) => `${i ? "L" : "M"}${((i / (vals.length - 1)) * width).toFixed(1)},${(height - ((v - min) / span) * (height - 2) - 1).toFixed(1)}`)
    .join(" ");
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-label={`trend from ${points[0][0]} to ${points[points.length - 1][0]}`}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.5" className="text-slate-500" />
    </svg>
  );
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded border bg-slate-50 px-3 py-2" title={hint}>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

export function Loading({ what }: { what: string }) {
  return <p className="animate-pulse text-slate-500">Loading {what}…</p>;
}

export function ErrorBox({ children }: { children: ReactNode }) {
  return <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">{children}</div>;
}

export const NA = "not available";
export const num = (v: number | null | undefined, digits = 2) =>
  v == null ? NA : v.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
export const cr = (v: number | null | undefined) => (v == null ? NA : `₹${Math.round(v).toLocaleString("en-IN")} Cr`);
export const pctTxt = (v: number | null | undefined, signed = false) =>
  v == null ? NA : `${signed && v > 0 ? "+" : ""}${v.toFixed(1)}%`;
