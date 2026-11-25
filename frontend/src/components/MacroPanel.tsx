import type { MacroPanel as M } from "@/lib/types";
import { Badge, Section, Sparkline, fmtDate } from "./ui";

export function MacroPanel({ macro, title }: { macro: M; title?: string }) {
  const s = macro.score;
  return (
    <Section
      title={title ?? `Economy check: ${macro.label}`}
      subtitle={
        s.judged
          ? `${s.tailwinds} tailwind${s.tailwinds === 1 ? "" : "s"}, ${s.headwinds} headwind${s.headwinds === 1 ? "" : "s"}, ${s.judged - s.tailwinds - s.headwinds} neutral, out of ${s.judged} drivers`
          : "No driver data available yet."
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-2 font-medium">Driver</th>
              <th className="py-1 pr-2 font-medium">Latest</th>
              <th className="py-1 pr-2 font-medium">Last 12 months</th>
              <th className="py-1 pr-2 font-medium">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {macro.drivers.map((d) => (
              <tr key={d.id} className="border-t align-top">
                <td className="py-2 pr-2">
                  <div className="font-medium">{d.label}</div>
                  <div className="text-xs text-slate-500">{d.why}</div>
                  <div className="text-[11px] text-slate-400">
                    Good for the industry when {d.good_when}. Source: {d.source}
                  </div>
                </td>
                <td className="whitespace-nowrap py-2 pr-2 tabular-nums">
                  {d.latest_text ?? "not available"}
                  <div className="text-[11px] text-slate-400">{d.latest_date ? fmtDate(d.latest_date) : ""}</div>
                </td>
                <td className="py-2 pr-2">
                  <Sparkline points={d.trend ?? []} />
                  <div className="text-[11px] text-slate-500">{d.change_text}</div>
                </td>
                <td className="py-2 pr-2">
                  <Badge value={d.verdict} />
                  <div className="mt-1 text-xs text-slate-500">{d.summary}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {macro.not_tracked.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">Also matters, but no free data source: {macro.not_tracked.join("; ")}.</p>
      )}
    </Section>
  );
}
