"""Fundamental scorecards for the investable universe, and universe-wide ranks (including a true
Greenblatt Magic Formula ranking).

Usage:
  python -m backend.score_universe fetch CACHE.json [--universe 800] [--budget 800]   # download (paced)
  python -m backend.score_universe score CACHE.json OUT_DIR                           # compute + write docs

The fetch step keeps a JSON cache of the raw Upstox data and refreshes the stalest companies first,
staying under Upstox's request limits. The score step writes one small JSON document per company
(OUT_DIR/<ISIN>.json) plus OUT_DIR/_summary.json, ready to store in the page's database.
Screening output only — not investment advice.
"""
import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import analysis, macro  # noqa: E402
from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.sources import upstox_bulk  # noqa: E402

ENDPOINTS = {k: v for k, v in upstox_bulk.ENDPOINTS.items() if k in ("profile", "income", "balance", "cashflow", "ratios", "holdings")}
FINANCIAL = {"banks", "nbfc"}
MF_EXCLUDED = FINANCIAL | {"power"}  # Greenblatt leaves out financials and utilities


class Pacer:
    """At most `rate` requests per second across threads (Upstox: ~2,000 per 30 minutes)."""

    def __init__(self, rate: float):
        self.gap, self.lock, self.next = 1 / rate, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.time()
            t = max(now, self.next)
            self.next = t + self.gap
        time.sleep(max(0, t - now))


def fetch(cache_path: Path, universe: int, budget: int, rate: float = 1.0) -> None:
    init_db()
    with SessionLocal() as s:
        rows, _ = build_rows(s)
    rows = [r for r in rows if r["close"] is not None][:universe]
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    now = datetime.now(timezone.utc)

    def age(isin):
        e = cache.get(isin)
        return 1e9 if not e else (now - datetime.fromisoformat(e["fetched_at"])).total_seconds() / 86400

    todo = sorted(rows, key=lambda r: -age(r["isin"]))
    todo = [r for r in todo if age(r["isin"]) > 6][:budget]
    pacer = Pacer(rate)
    done = 0
    with upstox_bulk._client() as c:
        for r in todo:
            data = {}
            for name, (path, params) in ENDPOINTS.items():
                pacer.wait()
                d = upstox_bulk._get(c, f"/fundamentals/{r['isin']}/{path}", params)
                if d is None and params.get("type") == "consolidated":
                    pacer.wait()
                    d = upstox_bulk._get(c, f"/fundamentals/{r['isin']}/{path}", {**params, "type": "standalone"})
                data[name] = d
            data["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if data.get("ratios") or data.get("income"):
                cache[r["isin"]] = data
            done += 1
            if done % 25 == 0:
                cache_path.write_text(json.dumps(cache, separators=(",", ":")))
                print(f"{done}/{len(todo)} fetched", flush=True)
    cache_path.write_text(json.dumps(cache, separators=(",", ":")))
    print(f"done: {done} fetched, cache holds {len(cache)} companies", flush=True)


def _pct_rank(values: dict[str, float], higher_better: bool) -> dict[str, float]:
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_better)
    n = len(items)
    return {k: (1 - i / (n - 1)) if n > 1 else 1.0 for i, (k, _) in enumerate(items)}


def clamp01(x):
    return max(0.0, min(1.0, x))


def card(isin: str, row: dict, raw: dict, macro_share: dict) -> dict:
    f = {k: {"data": v} for k, v in raw.items() if k != "fetched_at"}
    fin = analysis.financials(f)
    kr = analysis.key_ratios(f)
    sh = analysis.shareholding(f) if raw.get("holdings") else {"rows": [], "change_over_period": {}}
    profile = raw.get("profile") or {}
    ind = macro.resolve_industry(profile.get("sector"), row["name"], row.get("sector"))
    rows = fin["periods"]
    g = fin["growth"]

    def r_(name, key="company"):
        return (kr.get(name) or {}).get(key)

    cfo = [x["cfo_to_profit"] for x in rows[:3] if x["cfo_to_profit"] is not None]
    bs = analysis.latest_with(rows, "liabilities_to_equity")
    margins = [x["net_margin_pct"] for x in rows[:4] if x["net_margin_pct"] is not None]
    profits = [x["net_profit"] for x in rows if x["net_profit"] is not None]
    prom = next((x for x in sh["rows"] if x["key"] == "promoters"), None)
    fii = next((x for x in sh["rows"] if x["key"] == "fii"), None)
    latest_pct = lambda x: (x["values"][0]["pct"] if x and x["values"] else None)  # noqa: E731

    m = {
        "roe": r_("ROE"), "roce": r_("ROCE"), "roa": r_("ROA"),
        "pe": r_("P/E"), "pe_sector": r_("P/E", "sector"), "pb": r_("P/B"), "pb_sector": r_("P/B", "sector"),
        "ev_ebitda": r_("EV/EBITDA"), "ev_ebitda_sector": r_("EV/EBITDA", "sector"),
        "revenue_cagr": g.get("revenue_cagr_pct"), "profit_cagr": g.get("net_profit_cagr_pct"), "growth_years": g.get("years"),
        "net_margin": margins[0] if margins else None, "net_margin_old": margins[-1] if len(margins) > 1 else None,
        "cfo_to_profit": round(sum(cfo) / len(cfo), 2) if cfo else None,
        "liabilities_to_equity": bs.get("liabilities_to_equity") if bs else None,
        "current_ratio": analysis.latest_with(rows, "current_ratio").get("current_ratio"),
        "profitable_years": f"{sum(p > 0 for p in profits)}/{len(profits)}" if profits else None,
        "promoter_pct": latest_pct(prom), "promoter_change": sh["change_over_period"].get("promoters"),
        "fii_pct": latest_pct(fii), "fii_change": sh["change_over_period"].get("fii"),
        "revenue_latest": rows[0]["revenue"] if rows else None, "latest_period": rows[0]["period"] if rows else None,
        "market_cap_cr": (profile.get("sector_market_cap_inr") or {}).get("value"),
    }
    fin_co = ind in FINANCIAL

    # --- component scores (0..1); None when the inputs are missing
    q = []
    if m["roe"] is not None:
        q.append(clamp01(m["roe"] / 25))
    if m["roce"] is not None and not fin_co:
        q.append(clamp01(m["roce"] / 25))
    if m["cfo_to_profit"] is not None and not fin_co:
        q.append(clamp01(m["cfo_to_profit"] / 1.0))
    if m["liabilities_to_equity"] is not None and not fin_co:
        q.append(clamp01(1 - (m["liabilities_to_equity"] - 0.5) / 2))
    if m["net_margin"] is not None and m["net_margin_old"] is not None:
        q.append(1.0 if m["net_margin"] >= m["net_margin_old"] - 1 else 0.3)
    if profits:
        q.append(1.0 if all(p > 0 for p in profits) else 0.0)
    quality = sum(q) / len(q) if q else None

    gr = [clamp01((x + 5) / 25) for x in (m["revenue_cagr"], m["profit_cagr"]) if x is not None]
    growth = sum(gr) / len(gr) if gr else None

    v = []
    for a, b in (("pe", "pe_sector"), ("pb", "pb_sector"), ("ev_ebitda", "ev_ebitda_sector")):
        if m[a] and m[b] and m[a] > 0 and m[b] > 0:
            v.append(clamp01(1 - (m[a] / m[b] - 0.5) / 1.5))  # half the sector multiple = 1, double = 0
    if m["pe"] is not None and m["pe"] <= 0:
        v.append(0.0)
    value = sum(v) / len(v) if v else None

    own = None  # promoters raising or holding their stake is a good sign; companies without promoters are not scored here
    if m["promoter_change"] is not None and (m["promoter_pct"] or 0) > 0:
        own = clamp01(0.6 + m["promoter_change"] / 5)
    econ = macro_share.get(ind)

    graham = []
    if m["pe"] is not None:
        graham.append(("P/E ≤ 15", 0 < m["pe"] <= 15))
    if m["pe"] and m["pb"]:
        graham.append(("P/B ≤ 1.5 or P/E × P/B ≤ 22.5", m["pb"] <= 1.5 or (m["pe"] > 0 and m["pe"] * m["pb"] <= 22.5)))
    if m["current_ratio"] is not None and not fin_co:
        graham.append(("Current ratio ≥ 2", m["current_ratio"] >= 2))
    if profits:
        graham.append(("Profit every year", all(p > 0 for p in profits)))
    if m["revenue_latest"] is not None:
        graham.append(("Revenue ≥ ₹1,000 Cr", m["revenue_latest"] >= 1000))

    return {"isin": isin, "symbol": row["symbol"], "name": row["name"], "key": row["key"], "industry": ind,
            "industry_label": macro.load_industries()[ind]["label"], "sector": profile.get("sector") or row.get("sector"),
            "price": row["close"], "price_date": row["price_date"], "metrics": m,
            "scores": {"quality": quality, "growth": growth, "value": value, "ownership": own, "economy": econ},
            "graham": [{"test": t, "pass": ok} for t, ok in graham],
            "fetched_at": raw.get("fetched_at"), "source": "Upstox fundamentals (Analytics Token); prices: exchange close"}


def score(cache_path: Path, out_dir: Path) -> None:
    init_db()
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    by = {r["isin"]: r for r in rows}
    cache = json.loads(cache_path.read_text())
    shares = {iid: macro.industry_macro(iid)["score"]["share_tailwinds"] for iid in macro.load_industries()}
    cards = {i: card(i, by[i], raw, shares) for i, raw in cache.items() if i in by}

    # Greenblatt Magic Formula across the whole universe: rank on return on capital and on earnings yield
    elig = {i: c for i, c in cards.items() if c["industry"] not in MF_EXCLUDED and c["metrics"]["roce"] is not None
            and c["metrics"]["ev_ebitda"] and c["metrics"]["ev_ebitda"] > 0}
    roc_rank = {i: n + 1 for n, (i, _) in enumerate(sorted(elig.items(), key=lambda kv: -kv[1]["metrics"]["roce"]))}
    ey_rank = {i: n + 1 for n, (i, _) in enumerate(sorted(elig.items(), key=lambda kv: kv[1]["metrics"]["ev_ebitda"]))}
    combined = sorted(elig, key=lambda i: roc_rank[i] + ey_rank[i])
    mf_pct = _pct_rank({i: -(roc_rank[i] + ey_rank[i]) for i in elig}, True)
    for pos, i in enumerate(combined, 1):
        c = cards[i]["metrics"]
        cards[i]["magic_formula"] = {"rank": pos, "of": len(combined), "roc_rank": roc_rank[i], "ey_rank": ey_rank[i],
                                     "roc": c["roce"], "earnings_yield": round(100 / c["ev_ebitda"], 2)}
    for i, c in cards.items():
        if i not in elig:
            c["magic_formula"] = {"rank": None, "reason": "excluded (financial or utility)" if c["industry"] in MF_EXCLUDED else "ROCE or EV/EBITDA missing or negative"}

    weights = {"quality": 0.35, "value": 0.25, "growth": 0.2, "ownership": 0.1, "economy": 0.1}
    for i, c in cards.items():
        sc = dict(c["scores"])
        sc["magic_formula"] = mf_pct.get(i)
        have = {k: v for k, v in sc.items() if k in weights and v is not None}
        tot = sum(weights[k] for k in have)
        comp = round(sum(weights[k] * have[k] for k in have) / tot * 100) if tot >= 0.6 else None
        c["scores"] = {k: (round(v * 100) if v is not None else None) for k, v in sc.items()}
        c["composite"] = comp
        c["grade"] = None if comp is None else "A" if comp >= 75 else "B" if comp >= 62 else "C" if comp >= 50 else "D" if comp >= 38 else "E"
    ranked = sorted([c for c in cards.values() if c["composite"] is not None], key=lambda c: -c["composite"])
    for n, c in enumerate(ranked, 1):
        c["rank"] = n
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, c in cards.items():
        c["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (out_dir / f"{i}.json").write_text(json.dumps(c, default=str))
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "companies": len(cards),
               "ranked": len(ranked), "magic_formula_universe": len(combined), "prices_as_of": as_of,
               "weights": weights, "method": "Quality 35%, value 25%, growth 20%, ownership 10%, economy 10%. Magic Formula ranks all non-financial, non-utility companies on ROCE and earnings yield (1 ÷ EV/EBITDA) and adds the two ranks, as in Greenblatt's book.",
               "label": "Screening output from fundamentals. Not investment advice."}
    (out_dir / "_summary.json").write_text(json.dumps(summary))
    print(f"scored {len(cards)} companies, {len(ranked)} ranked, magic formula universe {len(combined)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "score"])
    ap.add_argument("cache")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--universe", type=int, default=800)
    ap.add_argument("--budget", type=int, default=800)
    ap.add_argument("--rate", type=float, default=1.0)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(Path(a.cache), a.universe, a.budget, a.rate)
    else:
        score(Path(a.cache), Path(a.out))
