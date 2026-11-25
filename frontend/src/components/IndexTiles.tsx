import { fmtAsOf, fmtPct, fmtPrice, pct, pctColor, type IndexTile, type Tick } from "@/lib/api";

export function IndexTiles({ tiles, ticks }: { tiles: IndexTile[]; ticks: Record<string, Tick> }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
      {tiles.map((t) => {
        const tick = ticks[t.key];
        const value = tick ? tick.ltp : t.close;
        const change = tick ? pct(tick.ltp, tick.cp) : t.change_pct;
        const asOf = tick ? fmtAsOf(tick.ltt) : fmtAsOf(t.as_of);
        const source = tick ? "Upstox live feed" : t.source ?? "no free end-of-day source; live only";
        return (
          <div key={t.label} className="rounded border bg-white p-3" title={`Source: ${source}`}>
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span className="font-medium text-slate-700">{t.label}</span>
              {tick && <span className="h-2 w-2 rounded-full bg-green-500" aria-label="live" />}
            </div>
            <div className="mt-1 text-lg font-semibold tabular-nums">{fmtPrice(value)}</div>
            <div className={`text-sm tabular-nums ${pctColor(change)}`}>{fmtPct(change)}</div>
            <div className="mt-1 text-[11px] text-slate-400">{asOf}</div>
          </div>
        );
      })}
    </div>
  );
}
