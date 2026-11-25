"""Every company in one industry, analysed on every number in the owner's framework, live.

Usage: python -m backend.industry_report <industry_key> OUT.json [--max 40]

For each listed company in the industry (most traded first): 4-5 years of margins, growth, returns
and leverage, a 3-year projection, valuation (P/E, P/B, EV/EBITDA vs sector and own history), DCF or
justified-P/B intrinsic value, Graham tests, Magic Formula measures, shareholding and free float,
index membership, volume and delivery %, share of the listed peers' revenue, and the latest news.
Writes OUT.json and OUT.json.db.json (fields for the page's industries/<id> document)."""
import argparse
import json
import os
import time
from datetime import datetime, timezone

os.environ.setdefault("RUN_JOBS", "false")
os.environ.setdefault("UPSTOX_ACCESS_TOKEN", "proxy-injected")

from backend.analyze_stock import projection  # noqa: E402
from backend.app import analysis, jobs, macro, valuation_methods  # noqa: E402
from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.app.stock import company_news, industry_news  # noqa: E402
from backend.sources import nse_delivery, nse_sectors, upstox_bulk, upstox_candles  # noqa: E402

ENDPOINTS = {k: v for k, v in upstox_bulk.ENDPOINTS.items() if k in ("profile", "income", "income_q", "balance", "cashflow", "ratios", "holdings", "actions")}


def fetch_fund(c, isin: str) -> dict:
    out = {}
    for name, (path, params) in ENDPOINTS.items():
        time.sleep(0.9)  # stay under Upstox's request limits
        d = upstox_bulk._get(c, f"/fundamentals/{isin}/{path}", params)
        if d is None and params.get("type") == "consolidated":
            time.sleep(0.9)
            d = upstox_bulk._get(c, f"/fundamentals/{isin}/{path}", {**params, "type": "standalone"})
        out[name] = {"data": d}
    return out


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("industry")
    ap.add_argument("out")
    ap.add_argument("--max", type=int, default=40)
    a = ap.parse_args()
    key = a.industry.replace("-", "_")
    init_db()
    jobs.refresh_instruments()
    jobs.refresh_sectors()
    jobs.refresh_prices()
    needed = {d["series"] for d in macro.load_industries()[key]["drivers"]}
    macro.refresh_macro(jobs.today_ist(), only=needed)
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    members = [r for r in rows if r.get("industry") == key and r["close"] is not None]
    members.sort(key=lambda r: -(r["turnover"] or 0))
    total_listed = len(members)
    members = members[: a.max]
    today = jobs.today_ist()
    delivery = nse_delivery.recent(today, 5)
    indices = nse_sectors.index_membership()
    ind_macro = macro.industry_macro(key)
    out = []
    with upstox_bulk._client() as c:
        for n, r in enumerate(members, 1):
            print(f"{n}/{len(members)} {r['symbol']}", flush=True)
            f = fetch_fund(c, r["isin"])
            fin = analysis.financials(f)
            kr = analysis.key_ratios(f)
            try:
                candles = upstox_candles._fetch(r["key"], today, None)
            except Exception:
                candles = []
            price = r["close"]
            val = analysis.valuation(key, f, fin, candles, price) if fin["periods"] else None
            proj = projection(fin) if fin["periods"] else {"available": False}
            sh = analysis.shareholding(f) if (f.get("holdings") or {}).get("data") else None
            prom = next((x for x in (sh or {}).get("rows", []) if x["key"] == "promoters"), None)
            prom_pct = prom["values"][0]["pct"] if prom and prom["values"] else None
            stats = analysis.price_stats(candles)
            profile = (f.get("profile") or {}).get("data") or {}
            q_rows = analysis._table(((f.get("income_q") or {}).get("data") or {}).get("income_statement"), "category")
            quarterly = {k: [{"period": p, "value": v} for p, v in sorted(vv.items(), key=lambda kv: analysis.period_end(kv[0]) or 0, reverse=True)][:4] for k, vv in q_rows.items()}
            out.append({
                "isin": r["isin"], "symbol": r["symbol"], "name": r["name"], "price": price, "price_date": r["price_date"],
                "basic_industry": profile.get("sector"), "description": (profile.get("company_profile") or "")[:500],
                "market_cap_cr": (profile.get("sector_market_cap_inr") or {}).get("value"),
                "financials": [{k: x[k] for k in ("period", "revenue", "operating_profit", "net_profit", "eps", "operating_margin_pct",
                                                   "net_margin_pct", "roe_pct", "cfo_to_profit", "current_ratio", "liabilities_to_equity",
                                                   "investing_cash_flow")} for x in fin["periods"][:5]],
                "quarterly": quarterly,
                "methods": valuation_methods.assess(key, fin, kr, price, candles, quarterly) if fin["periods"] else None,
                "growth": fin["growth"], "eps_adjustments": fin["eps_adjustments"], "projection": proj,
                "ratios": kr, "valuation": {k: val[k] for k in ("chosen", "why", "metrics", "label", "history")} if val else None,
                "dcf": analysis.dcf(key, fin, kr, price) if fin["periods"] else {"available": False, "reason": "No financials."},
                "graham": analysis.graham(key, fin, f, price) if fin["periods"] else [],
                "quality": analysis.quality(key, fin, kr) if fin["periods"] else None,
                "magic_formula": {"roc": (kr.get("ROCE") or {}).get("company"),
                                  "earnings_yield": round(100 / kr["EV/EBITDA"]["company"], 2) if (kr.get("EV/EBITDA") or {}).get("company") and kr["EV/EBITDA"]["company"] > 0 else None},
                "shareholding": sh, "free_float_pct": round(100 - prom_pct, 2) if prom_pct is not None else None,
                "indices": indices.get(r["isin"], []), "delivery": nse_delivery.summary(r["symbol"], delivery),
                "volume": r["volume"], "turnover": r["turnover"], "returns": {k: stats.get(k) for k in ("return_1m", "return_6m", "return_1y", "cagr_3y", "cagr_5y", "from_high_pct")} if stats.get("available") else None,
                "news": company_news(r["name"] or r["symbol"])["items"][:6],
            })
    # Industry view: share of listed peers' revenue, medians, Magic Formula rank within the industry
    rev = {x["isin"]: (x["financials"][0]["revenue"] if x["financials"] else None) for x in out}
    tot = sum(v for v in rev.values() if v)
    for x in out:
        x["revenue_share_pct"] = round(rev[x["isin"]] / tot * 100, 1) if rev[x["isin"]] and tot else None
    mf = [x for x in out if x["magic_formula"]["roc"] is not None and x["magic_formula"]["earnings_yield"] is not None]
    r1 = {x["isin"]: i for i, x in enumerate(sorted(mf, key=lambda x: -x["magic_formula"]["roc"]))}
    r2 = {x["isin"]: i for i, x in enumerate(sorted(mf, key=lambda x: -x["magic_formula"]["earnings_yield"]))}
    for i, x in enumerate(sorted(mf, key=lambda x: r1[x["isin"]] + r2[x["isin"]]), 1):
        x["magic_formula"]["industry_rank"] = i
        x["magic_formula"]["of"] = len(mf)
    med = lambda f: median([f(x) for x in out])  # noqa: E731
    medians = {
        "net_margin_pct": med(lambda x: x["financials"][0]["net_margin_pct"] if x["financials"] else None),
        "roe": med(lambda x: (x["ratios"].get("ROE") or {}).get("company")), "roce": med(lambda x: (x["ratios"].get("ROCE") or {}).get("company")),
        "pe": med(lambda x: (x["ratios"].get("P/E") or {}).get("company")), "pb": med(lambda x: (x["ratios"].get("P/B") or {}).get("company")),
        "ev_ebitda": med(lambda x: (x["ratios"].get("EV/EBITDA") or {}).get("company")),
        "revenue_cagr": med(lambda x: x["growth"].get("revenue_cagr_pct")), "profit_cagr": med(lambda x: x["growth"].get("net_profit_cagr_pct")),
    }
    stages = [x["methods"]["cycle"]["stage"] for x in out if x.get("methods") and x["methods"]["cycle"].get("cyclical")]
    g = valuation_methods.guide(key)
    cycle = {"cyclical": g["cyclical"]}
    if g["cyclical"]:
        cycle.update({"company_stages": {s: stages.count(s) for s in sorted(set(stages))},
                      "commodities": [c for c in (valuation_methods.commodity_position(s) for s in g["cycle_signals"]) if c]})
    report = {"industry": key, "valuation_guide": g, "cycle": cycle, "label": macro.load_industries()[key]["label"], "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "listed_companies": total_listed, "covered": len(out), "prices_as_of": as_of, "medians": medians, "macro": ind_macro,
              "industry_news": industry_news(macro.load_industries()[key]["label"])["items"][:10], "companies": out,
              "notes": "Revenue share is among the listed companies covered here, not the whole industry. Debt is not reported separately by the data source, so leverage uses total liabilities ÷ equity and DCF does not deduct debt. Methods that need figures not in the data feed (installed capacity for EV/replacement cost, embedded value, land NAV, segment profits) are filled in by the research step from annual reports and investor presentations.",
              "sources": "Upstox fundamentals and candles; NSE bhavcopy and delivery data; NSE index lists; MoSPI, RBI, FRED; Google News."}
    with open(a.out, "w") as fh:
        json.dump(report, fh, default=str)
    with open(a.out + ".db.json", "w") as fh:
        json.dump({"status": "working", "step": "Numbers done for every company. Now researching the industry from primary sources…",
                   "updated_at": report["generated_at"], "report": report}, fh, default=str)
    print(f"wrote {a.out}: {len(out)} of {total_listed} companies, {os.path.getsize(a.out) // 1024} KB")


if __name__ == "__main__":
    main()
