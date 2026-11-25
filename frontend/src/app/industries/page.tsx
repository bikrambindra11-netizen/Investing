"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge, ErrorBox, Loading } from "@/components/ui";
import { getJSON } from "@/lib/api";
import type { IndustrySummary } from "@/lib/types";

export default function IndustriesView() {
  const [list, setList] = useState<IndustrySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getJSON<IndustrySummary[]>("/api/industries").then(setList).catch((e) => setError(`Could not load industries (${e.message}).`));
  }, []);
  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!list) return <Loading what="industries" />;
  const sorted = [...list].sort((a, b) => (b.score.share_tailwinds ?? -1) - (a.score.share_tailwinds ?? -1));
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-bold">Industries</h1>
      <p className="text-sm text-slate-600">Sorted by how much of the economic backdrop is currently working for each industry.</p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {sorted.map((i) => {
          const s = i.score;
          const tone = s.share_tailwinds == null ? "neutral" : s.share_tailwinds >= 0.5 ? "tailwind" : s.headwinds > s.tailwinds ? "headwind" : "neutral";
          return (
            <Link key={i.id} href={`/industry/${i.id}`} className="rounded border bg-white p-3 hover:border-slate-400">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">{i.label}</span>
                <Badge value={tone} label={tone === "tailwind" ? "supportive" : tone === "headwind" ? "unfavourable" : "mixed"} />
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {s.tailwinds} tailwinds · {s.headwinds} headwinds · {s.judged} drivers · {i.stocks.toLocaleString("en-IN")} stocks
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
