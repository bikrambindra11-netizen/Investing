"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { MacroPanel } from "@/components/MacroPanel";
import { NewsList } from "@/components/NewsList";
import { PeersTable } from "@/components/PeersTable";
import { PriceChart } from "@/components/PriceChart";
import { Badge, ErrorBox, Loading, Section, Source, Stat, cr, fmtDate, num, pctTxt } from "@/components/ui";
import { API_BASE, fmtInt, fmtPct, fmtPrice, getJSON, pct, pctColor } from "@/lib/api";
import type { StockPage } from "@/lib/types";
import { useMarketStream } from "@/lib/useMarketStream";

export default function StockPageView() {
  const { isin } = useParams<{ isin: string }>();
  const [d, setD] = useState<StockPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { ticks } = useMarketStream();

  useEffect(() => {
    setD(null);
    getJSON<StockPage>(`/api/stock/${isin}`)
      .then(setD)
      .catch((e) => setError(`Could not load this stock (${e.message}). Is the backend running?`));
  }, [isin]);

  if (error) return <ErrorBox>{error}</ErrorBox>;
  if (!d) return <Loading what="stock analysis (first load can take a few seconds)" />;

  const tick = ticks[d.info.key];
  const price = tick?.ltp ?? d.quote.close;
  const change = tick ? pct(tick.ltp, tick.cp) : d.quote.change_pct;
  const s = d.stats;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-bold">{d.info.name}</h1>
          <p className="text-sm text-slate-500">
            {d.info.listings.map((l) => `${l.exchange}: ${l.symbol}`).join(" · ")} · ISIN {d.info.isin}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums">₹{fmtPrice(price)}</div>
          <div className={`text-sm tabular-nums ${pctColor(change)}`}>{fmtPct(change)}</div>
          <div className="text-[11px] text-slate-400">
            {tick ? `Live · Upstox · ${fmtDate(tick.ltt)}` : `${d.quote.price_source ?? "not available"} · close of ${fmtDate(d.quote.price_date)}`}
          </div>
        </div>
      </div>

      {d.fundamentals_status.needs_login && (
        <div className="rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          <b>Company financials need your Upstox login.</b> Price, industry, economy and news below work without it.
          The business, financials, Graham checks and valuation sections fill in after you log in.{" "}
          <a href={`${API_BASE}/auth/upstox/login`} className="ml-1 inline-block rounded bg-slate-900 px-3 py-1 text-white">Login with Upstox</a>
        </div>
      )}

      {/* Summary card */}
      <section className={`rounded border-2 p-4 ${d.summary.tone === "positive" ? "border-green-400 bg-green-50" : d.summary.tone === "negative" ? "border-red-300 bg-red-50" : "border-slate-300 bg-white"}`}>
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Summary</div>
        <p className="mt-1 text-lg font-semibold">{d.summary.verdict}</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
          {d.summary.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2 text-xs">
          <span className="rounded bg-white px-2 py-1 ring-1 ring-slate-200">Economy: {d.summary.scores.macro_share_tailwinds == null ? "not available" : `${Math.round(d.summary.scores.macro_share_tailwinds * 100)}% of drivers are tailwinds`}</span>
          <span className="rounded bg-white px-2 py-1 ring-1 ring-slate-200">Company: {d.summary.scores.micro == null ? "not available" : `${Math.round(d.summary.scores.micro * 100)}% of checks passed`}</span>
          <span className="rounded bg-white px-2 py-1 ring-1 ring-slate-200">Valuation: {d.summary.scores.valuation}</span>
        </div>
        <p className="mt-3 text-xs font-medium text-slate-600">{d.summary.label}</p>
      </section>

      {/* Price */}
      <Section title="Price">
        <PriceChart candles={d.candles} />
        {s.available ? (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="52-week high" value={`₹${fmtPrice(s.high_52w ?? null)}`} />
            <Stat label="52-week low" value={`₹${fmtPrice(s.low_52w ?? null)}`} />
            <Stat label="From 52-week high" value={pctTxt(s.from_high_pct, true)} />
            <Stat label="Avg daily volume (3 months)" value={fmtInt(s.avg_volume_3m ?? null)} />
            <Stat label="1 month" value={pctTxt(s.return_1m, true)} />
            <Stat label="6 months" value={pctTxt(s.return_6m, true)} />
            <Stat label="1 year" value={pctTxt(s.return_1y, true)} />
            <Stat label="5 years (a year)" value={pctTxt(s.cagr_5y, true)} hint="Compound annual growth of the share price" />
          </div>
        ) : null}
        <Source source={d.candles_meta.source} asOf={s.as_of} />
        {d.candles_meta.error && <p className="text-xs text-red-700">Price history error: {d.candles_meta.error}</p>}
      </Section>

      {/* Industry */}
      <Section title="Industry (detected automatically)">
        <ol className="grid gap-2 text-sm sm:grid-cols-4">
          {[
            ["Macro-economic sector", d.classification.macro_economic_sector, d.classification.sources.sector],
            ["Sector", d.classification.sector, d.classification.sources.sector],
            ["Industry", d.classification.industry, d.classification.sources.industry],
            ["Basic industry", d.classification.basic_industry, d.classification.sources.basic_industry],
          ].map(([label, value, src], i) => (
            <li key={label as string} className="rounded border bg-slate-50 px-3 py-2">
              <div className="text-[11px] text-slate-500">{i + 1}. {label}</div>
              <div className="font-medium">{value ?? "not available"}</div>
              <div className="text-[10px] text-slate-400">{src ?? (label === "Basic industry" ? "needs Upstox login" : "not in NSE index lists")}</div>
            </li>
          ))}
        </ol>
        <Link href={`/industry/${d.classification.industry_id}`} className="mt-3 inline-block text-sm text-blue-700 hover:underline">
          Open the {d.classification.industry} industry page →
        </Link>
      </Section>

      <MacroPanel macro={d.macro} />

      {/* Micro */}
      <Section title="1. Business" subtitle="What the company does">
        <p className="text-sm">{d.profile.description ?? "not available"}</p>
        {d.profile.market_cap_cr != null && <p className="mt-1 text-sm">Market value (Upstox): {cr(d.profile.market_cap_cr)}</p>}
        <Source source={d.fundamentals_status.source} asOf={d.profile.fetched_at} />
      </Section>

      <Section title="2. Industry position" subtitle="Competitors side by side (amber row = this stock)">
        <PeersTable peers={d.peers} highlight={d.info.isin} />
        <p className="mt-1 text-xs text-slate-500">Market share and capacity utilisation: not available from free sources.</p>
      </Section>

      {d.financials && (
        <Section title="3. Financials" subtitle={`₹ crore, consolidated where available. ${d.financials.years_available} years of data.`}>
          <FinancialsTable d={d} />
          <Source source={d.fundamentals_status.source} asOf={d.financials.fetched_at} />
        </Section>
      )}

      {d.quality && (
        <Section title="Business quality checks" subtitle={`${d.quality.passed} of ${d.quality.total} passed`}>
          <ul className="space-y-1 text-sm">
            {d.quality.items.map((q) => (
              <li key={q.name} className="flex gap-2"><Badge value={q.ok ? "pass" : "fail"} /> <span className="font-medium">{q.name}:</span> {q.value}</li>
            ))}
          </ul>
        </Section>
      )}

      {d.capital_allocation && (
        <Section title="4. Capital allocation" subtitle={d.capital_allocation.note}>
          <div className="flex flex-wrap gap-2 text-sm">
            {d.capital_allocation.investing_cash_flow.map((x) => <Stat key={x.period} label={x.period} value={cr(x.investing_cash_flow)} />)}
          </div>
          <h3 className="mt-3 text-sm font-medium">Dividends, bonuses, splits, buybacks</h3>
          {d.capital_allocation.events.length === 0 ? <p className="text-sm text-slate-500">None listed.</p> : (
            <ul className="mt-1 space-y-1 text-sm">
              {d.capital_allocation.events.map((e, i) => (
                <li key={i}>{e.date}: <b>{e.type}</b> {e.details ?? (e.amount != null ? `₹${e.amount}` : e.ratio ?? "")}</li>
              ))}
            </ul>
          )}
          <Source source={d.fundamentals_status.source} asOf={d.capital_allocation.fetched_at} />
        </Section>
      )}

      {d.shareholding && (
        <Section title="5. Shareholding" subtitle={`% of shares held, last ${d.shareholding.periods.length} quarters. Pledge: ${d.shareholding.pledge}.`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="text-left text-xs text-slate-500"><tr><th className="py-1 font-medium">Holder</th>{d.shareholding.periods.map((p) => <th key={p} className="py-1 text-right font-medium">{p}</th>)}<th className="py-1 text-right font-medium">Change</th></tr></thead>
              <tbody>
                {d.shareholding.rows.map((r) => (
                  <tr key={r.key} className="border-t">
                    <td className="py-1">{r.category}</td>
                    {r.values.map((v) => <td key={v.period} className="py-1 text-right tabular-nums">{v.pct == null ? "—" : `${v.pct}%`}</td>)}
                    <td className={`py-1 text-right tabular-nums ${pctColor(d.shareholding!.change_over_period[r.key] ?? null)}`}>
                      {d.shareholding!.change_over_period[r.key] == null ? "—" : `${d.shareholding!.change_over_period[r.key] > 0 ? "+" : ""}${d.shareholding!.change_over_period[r.key]} pts`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Source source={d.fundamentals_status.source} asOf={d.shareholding.fetched_at} />
        </Section>
      )}

      {d.valuation && (
        <Section title="6. Valuation" subtitle={d.valuation.why}>
          <div className="mb-2"><Badge value={d.valuation.label} label={`Looks ${d.valuation.label}`} /></div>
          <div className="grid gap-2 sm:grid-cols-2">
            {d.valuation.metrics.map((m) => (
              <div key={m.name} className="rounded border bg-slate-50 p-3 text-sm">
                <div className="font-semibold">{m.name}: {num(m.current)}</div>
                <div>Sector: {num(m.sector)}{m.vs_sector_pct != null && ` (${m.vs_sector_pct > 0 ? "+" : ""}${m.vs_sector_pct}% vs sector)`}</div>
                <div>Own {m.own_years}-year average: {num(m.own_avg)}{m.vs_own_pct != null && ` (${m.vs_own_pct > 0 ? "+" : ""}${m.vs_own_pct}% vs own history)`}</div>
              </div>
            ))}
          </div>
          <Source source={`${d.fundamentals_status.source}; history = year-end share price ÷ reported EPS / book value`} asOf={d.valuation.fetched_at} />
        </Section>
      )}

      {d.graham && (
        <Section title="7. Graham's defensive investor checks" subtitle="Benjamin Graham's tests for a conservative investor. Each shows the number behind it.">
          <ul className="space-y-2 text-sm">
            {d.graham.map((g) => (
              <li key={g.name} className="flex gap-2">
                <Badge value={g.status} />
                <div>
                  <span className="font-medium">{g.name}</span> <span className="text-slate-500">({g.rule})</span>
                  <div>{g.value ?? "not available"}</div>
                  {g.note && <div className="text-xs text-slate-500">{g.note}</div>}
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="8. Key risks">
        {d.risks.length === 0 ? <p className="text-sm text-slate-500">No specific red flags found in the available data.</p> : (
          <ul className="list-disc space-y-1 pl-5 text-sm">{d.risks.map((r) => <li key={r}>{r}</li>)}</ul>
        )}
      </Section>

      <NewsList news={d.news} title="News" />
    </div>
  );
}

function FinancialsTable({ d }: { d: StockPage }) {
  const rows = d.financials!.periods.slice(0, 6);
  const lines: [string, (r: (typeof rows)[number]) => string][] = [
    ["Revenue", (r) => cr(r.revenue)],
    ["Operating profit", (r) => cr(r.operating_profit)],
    ["Net profit", (r) => cr(r.net_profit)],
    ["EPS (₹)", (r) => num(r.eps)],
    ["Operating margin", (r) => pctTxt(r.operating_margin_pct)],
    ["Net margin", (r) => pctTxt(r.net_margin_pct)],
    ["Return on equity", (r) => pctTxt(r.roe_pct)],
    ["Cash from operations", (r) => cr(r.cash_from_operations)],
    ["Cash from operations ÷ profit", (r) => num(r.cfo_to_profit)],
    ["Current ratio", (r) => num(r.current_ratio)],
    ["Total liabilities ÷ equity", (r) => num(r.liabilities_to_equity)],
  ];
  const g = d.financials!.growth;
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-xs text-slate-500"><tr><th className="py-1 text-left font-medium" />{rows.map((r) => <th key={r.period} className="py-1 text-right font-medium">{r.period}</th>)}</tr></thead>
          <tbody>
            {lines.map(([label, f]) => (
              <tr key={label} className="border-t"><td className="py-1 pr-2">{label}</td>{rows.map((r) => <td key={r.period} className="py-1 text-right tabular-nums">{f(r)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-sm">
        Growth per year over {g.years ?? "—"} years: revenue {pctTxt(g.revenue_cagr_pct ?? null)}, operating profit {pctTxt(g.operating_profit_cagr_pct ?? null)}, net profit {pctTxt(g.net_profit_cagr_pct ?? null)}.
      </p>
      <p className="text-xs text-slate-500">
        Not reported by the source, so not shown: EBITDA, debt, interest cover, working-capital days.
        {d.financials!.eps_adjustments.length > 0 && ` EPS adjusted for bonus/split between ${d.financials!.eps_adjustments.map((a) => a.between).join(", ")}.`}
      </p>
    </>
  );
}
