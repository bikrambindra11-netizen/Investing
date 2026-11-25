import type { News } from "@/lib/types";
import { Badge, Section, fmtDate } from "./ui";

export function NewsList({ news, title }: { news: News; title: string }) {
  return (
    <Section title={title} subtitle="Headlines tagged positive / negative / neutral by simple word rules. Read the article before acting.">
      {news.error && <p className="text-sm text-red-700">News could not be loaded right now ({news.error}).</p>}
      {!news.error && news.items.length === 0 && <p className="text-sm text-slate-500">No recent news found.</p>}
      <ul className="space-y-2">
        {news.items.map((n) => (
          <li key={n.link} className="flex gap-2 text-sm">
            <Badge value={n.sentiment} />
            <div className="min-w-0">
              <a href={n.link} target="_blank" rel="noopener noreferrer" className="hover:underline">
                {n.title}
              </a>
              <div className="text-[11px] text-slate-400">
                {n.publisher ?? "unknown publisher"} · {fmtDate(n.published)}
              </div>
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px] text-slate-400">Source: {news.source}{news.fetched_at ? ` · fetched ${fmtDate(news.fetched_at)}` : ""}</p>
    </Section>
  );
}
