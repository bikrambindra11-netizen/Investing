export type Verdict = "tailwind" | "neutral" | "headwind" | "not available";

export type Driver = {
  id: string;
  label: string;
  unit: string;
  source: string;
  verdict: Verdict;
  summary: string;
  latest: number | null;
  latest_date?: string;
  latest_text?: string;
  change_text?: string | null;
  trend?: [string, number][];
  why?: string;
  good_when?: string;
};

export type MacroPanel = {
  industry: string;
  label: string;
  drivers: Driver[];
  not_tracked: string[];
  score: { tailwinds: number; headwinds: number; judged: number; share_tailwinds: number | null };
};

export type NewsItem = { title: string; link: string; publisher: string | null; published: string | null; sentiment: "positive" | "negative" | "neutral" };
export type News = { items: NewsItem[]; fetched_at?: string; source: string; error?: string };

export type Peer = {
  isin: string; symbol: string; name: string | null; key: string;
  close: number | null; change_pct: number | null; turnover: number | null; price_date: string | null;
  sector: string | null; pe: number | null; pb: number | null; roe: number | null; roce: number | null;
  ev_ebitda: number | null; ratios_fetched_at: string | null;
};

export type Candle = { date: string; open: number; high: number; low: number; close: number; volume: number };

export type FinRow = {
  period: string; revenue: number | null; operating_profit: number | null; profit_before_tax: number | null;
  net_profit: number | null; eps: number | null; operating_margin_pct: number | null; net_margin_pct: number | null;
  roe_pct: number | null; cash_from_operations: number | null; cfo_to_profit: number | null;
  investing_cash_flow: number | null; equity: number | null; current_ratio: number | null;
  liabilities_to_equity: number | null;
};

export type GrahamCheck = { name: string; status: "pass" | "fail" | "partial" | "not_available" | "skipped"; value: string | null; rule: string; note: string | null };

export type ValMetric = { name: string; current: number | null; sector: number | null; own_avg: number | null; own_years: number; vs_sector_pct: number | null; vs_own_pct: number | null };

export type StockPage = {
  info: { isin: string; name: string | null; symbol: string; key: string; listings: { exchange: string; symbol: string; key: string; series: string | null }[]; nse_sector: string | null };
  quote: { close: number | null; prev_close: number | null; change_pct: number | null; volume: number | null; turnover: number | null; price_date: string | null; price_source: string | null; live: { ltp: number; cp: number | null; ltt: string | null } | null };
  candles: Candle[];
  candles_meta: { source: string; fetched_at: string | null; error: string | null };
  stats: { available: boolean; as_of?: string; close?: number; high_52w?: number; low_52w?: number; from_high_pct?: number; return_1m?: number | null; return_6m?: number | null; return_1y?: number | null; cagr_3y?: number | null; cagr_5y?: number | null; avg_volume_3m?: number | null };
  classification: { macro_economic_sector: string | null; sector: string | null; industry: string; basic_industry: string | null; industry_id: string; sources: Record<string, string | null> };
  profile: { description: string | null; market_cap_cr: number | null; fetched_at: string | null };
  fundamentals_status: { available: boolean; needs_login: boolean; errors: Record<string, string>; source: string };
  financials: { periods: FinRow[]; growth: Record<string, number | null>; eps_adjustments: { between: string; ratio: number }[]; years_available: number; units: string; fetched_at: string | null } | null;
  quality: { items: { name: string; ok: boolean; value: string }[]; passed: number; total: number } | null;
  capital_allocation: { events: { type: string; date: string; amount: number | null; ratio: string | null; details: string | null }[]; investing_cash_flow: { period: string; investing_cash_flow: number | null }[]; note: string; fetched_at: string | null } | null;
  shareholding: { periods: string[]; rows: { category: string; key: string; values: { period: string; pct: number | null }[] }[]; change_over_period: Record<string, number>; fetched_at: string | null; pledge: string } | null;
  valuation: { chosen: string[]; why: string; metrics: ValMetric[]; label: string; history: { period: string; price: number | null; pe: number | null; pb: number | null }[]; fetched_at: string | null } | null;
  graham: GrahamCheck[] | null;
  risks: string[];
  macro: MacroPanel;
  peers: Peer[];
  news: News;
  summary: { verdict: string; tone: "positive" | "negative" | "neutral"; reasons: string[]; scores: { macro_share_tailwinds: number | null; micro: number | null; valuation: string }; label: string };
};

export type IndustryPage = {
  id: string; label: string; macro: MacroPanel; peers: Peer[]; total_members: number; news: News; membership_note: string;
};

export type IndustrySummary = { id: string; label: string; stocks: number; score: MacroPanel["score"] };
