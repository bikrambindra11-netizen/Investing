"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";
import type { Candle } from "@/lib/types";

const RANGES: [string, number][] = [["1M", 31], ["6M", 183], ["1Y", 366], ["3Y", 1096], ["5Y", 1827], ["10Y", 3653]];

export function PriceChart({ candles }: { candles: Candle[] }) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const [range, setRange] = useState(366);

  useEffect(() => {
    if (!box.current) return;
    const c = createChart(box.current, {
      height: 280,
      layout: { background: { color: "#ffffff" }, textColor: "#475569" },
      grid: { vertLines: { visible: false }, horzLines: { color: "#f1f5f9" } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      autoSize: true,
    });
    series.current = c.addAreaSeries({ lineColor: "#0f172a", topColor: "rgba(15,23,42,0.15)", bottomColor: "rgba(15,23,42,0)", lineWidth: 2 });
    chart.current = c;
    return () => c.remove();
  }, []);

  useEffect(() => {
    if (!series.current || !candles.length) return;
    const last = new Date(candles[candles.length - 1].date + "T00:00:00");
    const from = new Date(last.getTime() - range * 86400000).toISOString().slice(0, 10);
    series.current.setData(candles.filter((c) => c.date >= from).map((c) => ({ time: c.date, value: c.close })));
    chart.current?.timeScale().fitContent();
  }, [candles, range]);

  return (
    <div>
      <div className="mb-2 flex gap-1">
        {RANGES.map(([label, days]) => (
          <button key={label} onClick={() => setRange(days)}
            className={`rounded px-2 py-0.5 text-xs ${range === days ? "bg-slate-900 text-white" : "border text-slate-600"}`}>
            {label}
          </button>
        ))}
      </div>
      {candles.length ? <div ref={box} className="h-[280px] w-full" /> : <p className="text-sm text-slate-500">Price history not available.</p>}
    </div>
  );
}
