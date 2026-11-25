"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  createChart, CrosshairMode, LineStyle, type IChartApi, type ISeriesApi, type SeriesMarker, type Time, type UTCTimestamp,
} from "lightweight-charts";
import { API_BASE } from "@/lib/api";

type Level = { level: number; touches: number; kind: string; distance_pct: number };
type ChartData = {
  tf: string; price: number; last_time: string; error?: string;
  candles: { time: number; open: number; high: number; low: number; close: number; volume: number }[];
  mas: { name: string; values: (number | null)[] }[];
  vwap: (number | null)[] | null;
  bollinger: { upper: (number | null)[]; lower: (number | null)[] };
  supertrend: { values: (number | null)[]; direction: (number | null)[] };
  rsi: (number | null)[];
  macd: { line: (number | null)[]; signal: (number | null)[]; hist: (number | null)[] };
  supports: Level[]; resistances: Level[];
  fibonacci: { levels: { ratio: number; price: number }[]; extensions: { ratio: number; price: number }[]; reading: string } | null;
  trend_lines: { kind: string; from_time: number; last_time: number; value_from: number; value_to: number; touches: number }[];
  patterns: { time: number; pattern: string; meaning: string }[];
  chart_patterns: { pattern: string; neckline: number; level: number; meaning: string }[];
  pivots: { pivot: number; r1: number; s1: number; r2: number; s2: number } | null;
  structure: string;
};

export const TIMEFRAMES = [
  ["1m", "1 min"], ["5m", "5 min"], ["15m", "15 min"], ["30m", "30 min"], ["1h", "1 hour"], ["1D", "Daily"], ["1W", "Weekly"], ["1M", "Monthly"],
] as const;
const OVERLAYS = [
  ["levels", "Support / resistance"], ["fib", "Fibonacci"], ["trend", "Trend lines"], ["patterns", "Candle patterns"],
  ["mas", "Moving averages"], ["vwap", "VWAP"], ["supertrend", "Supertrend"], ["bb", "Bollinger"], ["pivots", "Pivots"], ["necks", "Pattern necklines"],
] as const;
type Overlay = (typeof OVERLAYS)[number][0];
const IST = 19800; // show Indian time on the chart's time axis
const BEAR = new Set(["Bearish engulfing", "Shooting star", "Evening star", "Three black crows", "Bearish marubozu", "Bearish harami", "Gap down"]);
const MA_COLORS = ["#2563eb", "#7c3aed", "#db2777"];
const css = (v: string, fb: string) => (typeof window === "undefined" ? fb : getComputedStyle(document.documentElement).getPropertyValue(v).trim() || fb);

function isMarketOpen() {
  const now = new Date(Date.now() + (new Date().getTimezoneOffset() + 330) * 60000);
  const m = now.getHours() * 60 + now.getMinutes();
  return now.getDay() >= 1 && now.getDay() <= 5 && m >= 555 && m <= 930;
}

export function TradingChart({ instrumentKey, symbol }: { instrumentKey: string; symbol: string }) {
  const [tf, setTf] = useState<string>("1D");
  const [data, setData] = useState<ChartData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [on, setOn] = useState<Record<Overlay, boolean>>({
    levels: true, fib: true, trend: true, patterns: true, mas: true, vwap: true, supertrend: false, bb: false, pivots: false, necks: true,
  });
  const mainRef = useRef<HTMLDivElement>(null), rsiRef = useRef<HTMLDivElement>(null), macdRef = useRef<HTMLDivElement>(null);

  // Load (and keep refreshing intraday data while the market is open)
  useEffect(() => {
    let stop = false;
    const load = () =>
      fetch(`${API_BASE}/api/chart?key=${encodeURIComponent(instrumentKey)}&tf=${tf}&bars=${tf === "1m" ? 750 : 600}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then((d) => { if (!stop) { setData(d); setError(d.error ?? null); } })
        .catch((e) => !stop && setError(`Chart data could not be loaded (${e.message}).`));
    setData(null);
    load();
    const id = setInterval(() => { if (["1m", "5m", "15m", "30m", "1h", "1D"].includes(tf) && isMarketOpen()) load(); }, 30000);
    return () => { stop = true; clearInterval(id); };
  }, [instrumentKey, tf]);

  // Draw
  useEffect(() => {
    if (!data || !data.candles.length || !mainRef.current || !rsiRef.current || !macdRef.current) return;
    const text = css("--chart-text", "#475569"), grid = css("--chart-grid", "#eef2f0");
    const up = "#12733f", down = "#b42318";
    const opts = {
      layout: { background: { color: "transparent" }, textColor: text, fontSize: 11 },
      grid: { vertLines: { color: grid }, horzLines: { color: grid } },
      crosshair: { mode: CrosshairMode.Normal }, autoSize: true,
      timeScale: { timeVisible: ["1m", "5m", "15m", "30m", "1h"].includes(tf), secondsVisible: false, borderVisible: false },
      rightPriceScale: { borderVisible: false },
    };
    const main = createChart(mainRef.current, { ...opts, height: 460 });
    const rsiC = createChart(rsiRef.current, { ...opts, height: 110 });
    const macdC = createChart(macdRef.current, { ...opts, height: 120 });
    const t = (s: number) => (s + IST) as UTCTimestamp;
    const times = data.candles.map((c) => t(c.time));
    const line = (vals: (number | null)[]) => vals.map((v, i) => (v == null ? null : { time: times[i], value: v })).filter(Boolean) as { time: Time; value: number }[];

    const candle = main.addCandlestickSeries({ upColor: up, downColor: down, borderVisible: false, wickUpColor: up, wickDownColor: down });
    candle.setData(data.candles.map((c) => ({ time: t(c.time), open: c.open, high: c.high, low: c.low, close: c.close })));
    const vol = main.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" } });
    main.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    vol.setData(data.candles.map((c) => ({ time: t(c.time), value: c.volume, color: c.close >= c.open ? "rgba(18,115,63,.35)" : "rgba(180,35,24,.35)" })));

    if (on.mas) data.mas.forEach((m, i) => main.addLineSeries({ color: MA_COLORS[i % 3], lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: m.name }).setData(line(m.values)));
    if (on.vwap && data.vwap) main.addLineSeries({ color: "#f59e0b", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "VWAP" }).setData(line(data.vwap));
    if (on.bb) {
      for (const k of ["upper", "lower"] as const) main.addLineSeries({ color: "#94a3b8", lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false }).setData(line(data.bollinger[k]));
    }
    if (on.supertrend) {
      const st = main.addLineSeries({ lineWidth: 2, priceLineVisible: false, lastValueVisible: false, title: "Supertrend" });
      st.setData(data.supertrend.values.map((v, i) => (v == null ? null : { time: times[i], value: v, color: data.supertrend.direction[i] === 1 ? up : down })).filter(Boolean) as { time: Time; value: number; color: string }[]);
    }
    const pl = (price: number, color: string, title: string, style = LineStyle.Dashed, width: 1 | 2 = 1) =>
      candle.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title });
    if (on.levels) {
      data.supports.forEach((l) => pl(l.level, up, `S (${l.touches})`, LineStyle.Dashed, 2));
      data.resistances.forEach((l) => pl(l.level, down, `R (${l.touches})`, LineStyle.Dashed, 2));
    }
    if (on.fib && data.fibonacci) data.fibonacci.levels.forEach((l) => pl(l.price, "#b7791f", `Fib ${l.ratio}`, LineStyle.Dotted));
    if (on.pivots && data.pivots) (["s2", "s1", "pivot", "r1", "r2"] as const).forEach((k) => pl(data.pivots![k], "#64748b", k.toUpperCase(), LineStyle.SparseDotted));
    if (on.necks) data.chart_patterns.forEach((p) => pl(p.neckline, "#0ea5e9", `${p.pattern} neckline`, LineStyle.LargeDashed));
    if (on.trend) data.trend_lines.forEach((tl) =>
      main.addLineSeries({ color: "#0d5c4a", lineWidth: 2, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
        .setData([{ time: t(tl.from_time), value: tl.value_from }, { time: t(tl.last_time), value: tl.value_to }]));
    if (on.patterns) {
      const marks: SeriesMarker<Time>[] = data.patterns.map((p) => {
        const bear = BEAR.has(p.pattern);
        return { time: t(p.time), position: bear ? "aboveBar" : "belowBar", color: bear ? down : up, shape: bear ? "arrowDown" : "arrowUp", text: p.pattern };
      });
      candle.setMarkers(marks.sort((a, b) => (a.time as number) - (b.time as number)));
    }

    const rsi = rsiC.addLineSeries({ color: "#7c3aed", lineWidth: 1, title: "RSI 14" });
    rsi.setData(line(data.rsi));
    rsi.createPriceLine({ price: 70, color: "#b42318", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "70" });
    rsi.createPriceLine({ price: 30, color: "#12733f", lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: "30" });
    macdC.addHistogramSeries({ title: "MACD hist" }).setData(data.macd.hist.map((v, i) => (v == null ? null : { time: times[i], value: v, color: v >= 0 ? "rgba(18,115,63,.6)" : "rgba(180,35,24,.6)" })).filter(Boolean) as { time: Time; value: number; color: string }[]);
    macdC.addLineSeries({ color: "#2563eb", lineWidth: 1, title: "MACD" }).setData(line(data.macd.line));
    macdC.addLineSeries({ color: "#f59e0b", lineWidth: 1, title: "Signal" }).setData(line(data.macd.signal));

    // keep the three panes scrolled together
    const charts: IChartApi[] = [main, rsiC, macdC];
    charts.forEach((c) => c.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (!r) return;
      charts.forEach((o) => o !== c && o.timeScale().setVisibleLogicalRange(r));
    }));
    const visible = { "1m": 200, "5m": 200, "15m": 200, "30m": 200, "1h": 200, "1D": 180, "1W": 150, "1M": 150 }[tf] ?? 180;
    main.timeScale().setVisibleLogicalRange({ from: data.candles.length - visible, to: data.candles.length + 3 });
    return () => charts.forEach((c) => c.remove());
  }, [data, on, tf]);

  const notes = useMemo(() => {
    if (!data || !data.candles.length) return null;
    return data;
  }, [data]);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        {TIMEFRAMES.map(([k, label]) => (
          <button key={k} onClick={() => setTf(k)} className={`rounded px-2.5 py-1 text-xs ${tf === k ? "bg-slate-900 text-white" : "border text-slate-600"}`}>{label}</button>
        ))}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600">
        {OVERLAYS.map(([k, label]) => (
          <label key={k} className="flex items-center gap-1">
            <input type="checkbox" checked={on[k]} onChange={(e) => setOn({ ...on, [k]: e.target.checked })} /> {label}
          </label>
        ))}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      {!data && !error && <p className="animate-pulse text-sm text-slate-500">Loading {symbol} {tf} chart…</p>}
      <div ref={mainRef} className="w-full" style={{ height: 460 }} />
      <div ref={rsiRef} className="w-full" style={{ height: 110 }} />
      <div ref={macdRef} className="w-full" style={{ height: 120 }} />
      {notes && (
        <div className="grid gap-2 text-xs sm:grid-cols-2">
          <div className="rounded border bg-slate-50 p-2"><b>Structure ({tf}):</b> {notes.structure}</div>
          {notes.fibonacci && <div className="rounded border bg-slate-50 p-2"><b>Fibonacci:</b> {notes.fibonacci.reading}</div>}
          {notes.trend_lines.map((tl, i) => <div key={i} className="rounded border bg-slate-50 p-2"><b>Trend line:</b> {tl.kind}, {tl.touches} touches, now at ₹{tl.value_to.toLocaleString("en-IN")}</div>)}
          {notes.chart_patterns.map((p, i) => <div key={i} className="rounded border bg-slate-50 p-2"><b>{p.pattern}:</b> {p.meaning} (neckline ₹{p.neckline.toLocaleString("en-IN")})</div>)}
          {notes.patterns.slice(-4).reverse().map((p, i) => <div key={i} className="rounded border bg-slate-50 p-2"><b>{p.pattern}</b> ({new Date((p.time + 0) * 1000).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: tf.endsWith("m") || tf === "1h" ? "2-digit" : undefined, minute: tf.endsWith("m") || tf === "1h" ? "2-digit" : undefined })}): {p.meaning}</div>)}
        </div>
      )}
      <p className="text-[11px] text-slate-400">Source: Upstox candles{data ? ` · last candle ${data.last_time.replace("T", " ").slice(0, 16)} IST` : ""}. Intraday timeframes refresh every 30 seconds during market hours. Chart facts, not buy/sell signals.</p>
    </div>
  );
}

export function MultiTimeframe({ instrumentKey }: { instrumentKey: string }) {
  type Row = { tf: string; structure?: string; rsi?: number | null; supertrend?: string | null; macd_above_signal?: boolean | null;
    vs_mas?: { name: string; value: number; above: boolean }[]; vwap?: number | null; support?: number | null; resistance?: number | null; error?: string };
  const [rows, setRows] = useState<Row[] | null>(null);
  useEffect(() => {
    fetch(`${API_BASE}/api/mtf?key=${encodeURIComponent(instrumentKey)}`).then((r) => r.json()).then(setRows).catch(() => setRows([]));
  }, [instrumentKey]);
  if (!rows) return <p className="animate-pulse text-sm text-slate-500">Checking every timeframe…</p>;
  const label = Object.fromEntries(TIMEFRAMES);
  const fmt = (v?: number | null) => (v == null ? "—" : `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-sm">
        <thead className="text-left text-xs text-slate-500"><tr><th className="py-1 pr-2 font-medium">Timeframe</th><th className="py-1 pr-2 font-medium">Structure</th><th className="py-1 pr-2 font-medium">Price vs averages</th><th className="py-1 pr-2 text-right font-medium">RSI</th><th className="py-1 pr-2 font-medium">Supertrend</th><th className="py-1 pr-2 font-medium">MACD</th><th className="py-1 pr-2 text-right font-medium">Nearest support</th><th className="py-1 pr-2 text-right font-medium">Nearest resistance</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.tf} className="border-t align-top">
              <td className="py-1.5 pr-2 font-medium">{label[r.tf as keyof typeof label] ?? r.tf}</td>
              {r.error ? <td colSpan={7} className="py-1.5 text-xs text-slate-400">{r.error}</td> : (<>
                <td className="py-1.5 pr-2 text-xs">{r.structure}</td>
                <td className="py-1.5 pr-2 text-xs">{(r.vs_mas ?? []).map((m) => `${m.above ? "above" : "below"} ${m.name}`).join(", ")}{r.vwap ? `, ${r.vs_mas && r.vwap ? "" : ""}VWAP ${fmt(r.vwap)}` : ""}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{r.rsi ?? "—"}</td>
                <td className="py-1.5 pr-2 text-xs">{r.supertrend ?? "—"}</td>
                <td className="py-1.5 pr-2 text-xs">{r.macd_above_signal == null ? "—" : r.macd_above_signal ? "above signal" : "below signal"}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{fmt(r.support)}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{fmt(r.resistance)}</td>
              </>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 text-[11px] text-slate-400">Each row is computed live from that timeframe&apos;s candles. When most rows agree, the timeframes are aligned; when they disagree, the short-term and long-term pictures differ.</p>
    </div>
  );
}
