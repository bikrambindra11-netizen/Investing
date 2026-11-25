"use client";

import { useEffect, useState } from "react";
import { ErrorBox, Loading, Section, Sparkline, fmtDate } from "@/components/ui";
import { getJSON } from "@/lib/api";
import type { Driver } from "@/lib/types";

export default function EconomyView() {
  const [d, setD] = useState<{ indicators: Driver[]; status?: { ok: boolean; detail: string; at: string } } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getJSON<{ indicators: Driver[] }>("/api/macro").then(setD).catch((e) => setError(`Could not load economic data (${e.message}).`));
  }, []);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Loading what="economic data" />;
  const missing = d.indicators.filter((i) => i.latest == null).length;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-bold">Economy</h1>
      {missing === d.indicators.length && (
        <p className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Economic data is still downloading (takes 2–3 minutes after the first start). Refresh this page shortly.
        </p>
      )}
      <Section title="All tracked indicators" subtitle={d.status ? `Last update: ${fmtDate(d.status.at)} — ${d.status.detail}` : undefined}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left text-xs text-slate-500">
              <tr><th className="py-1 font-medium">Indicator</th><th className="py-1 font-medium">Latest</th><th className="py-1 font-medium">Trend</th><th className="py-1 font-medium">Change</th><th className="py-1 font-medium">Source</th></tr>
            </thead>
            <tbody>
              {d.indicators.map((i) => (
                <tr key={i.id} className="border-t">
                  <td className="py-1.5 pr-2">{i.label}</td>
                  <td className="whitespace-nowrap py-1.5 pr-2 tabular-nums">{i.latest_text ?? "not available"}<div className="text-[11px] text-slate-400">{i.latest_date ? fmtDate(i.latest_date) : ""}</div></td>
                  <td className="py-1.5 pr-2"><Sparkline points={i.trend ?? []} /></td>
                  <td className="py-1.5 pr-2 text-xs text-slate-600">{i.change_text ?? "—"}</td>
                  <td className="py-1.5 text-xs text-slate-500">{i.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
