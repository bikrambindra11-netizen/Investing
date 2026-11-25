"""The full, precomputed card for every company: scorecard, statement analysis (P&L, balance sheet, cash
flow, DuPont, Piotroski, Altman), industry-specific valuation and cycle, DCF, Graham, shareholding, peers
and market share, free float, indices, delivery, and the framework checklist answered from the numbers.

Usage: python -m backend.build_cards CACHE.json OUT_DIR [--chunk-kb 230]

Writes OUT_DIR/fund/cNNN.json (companies grouped into documents under the database's size limit, by a
hash of the ISIN the page also computes), OUT_DIR/fund/meta.json, and OUT_DIR/fund/industries.json."""
import argparse
import base64
import gzip
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("RUN_JOBS", "false")

from backend.analyze_stock import projection  # noqa: E402
from backend.app import analysis, checklist, jobs, macro, statements, valuation_methods  # noqa: E402
from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.score_universe import compute  # noqa: E402
from backend.sources import nse_delivery, nse_sectors  # noqa: E402

KEEP_YEAR = ["period", "revenue", "other_income", "expenses", "pbt", "tax", "pat", "eps", "pbt_margin_pct", "net_margin_pct",
             "tax_rate_pct", "other_income_share_pct", "total_assets", "non_current_assets", "current_assets", "current_liabilities",
             "non_current_liabilities", "equity", "working_capital", "book_value_per_share", "shares_cr", "current_ratio",
             "liabilities_to_equity", "long_term_liabilities_to_assets", "roe_pct", "roa_pct", "pretax_roce_pct", "asset_turnover",
             "equity_multiplier", "cfo", "cfi", "cff", "free_cash_flow", "change_in_wc", "cash_end", "cfo_to_pat", "fcf_margin_pct",
             "reinvestment_rate_pct", "accruals_to_assets_pct", "revenue_growth_pct", "pat_growth_pct", "eps_growth_pct",
             "book_value_growth_pct", "share_count_change_pct"]


def bucket(isin: str, n: int) -> int:
    """FNV-1a hash of the ISIN, mod n (the page computes the same to find a company's document)."""
    h = 2166136261
    for ch in isin:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h % n


def _round(o):
    if isinstance(o, float):
        return round(o, 2)
    if isinstance(o, dict):
        return {k: _round(v) for k, v in o.items() if v is not None}
    if isinstance(o, list):
        return [_round(v) for v in o]
    return o


def median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2, 2)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cache")
    ap.add_argument("out")
    ap.add_argument("--chunk-kb", type=int, default=230)
    a = ap.parse_args()
    init_db()
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    by = {r["isin"]: r for r in rows}
    cache = json.loads(Path(a.cache).read_text())
    cards, summary = compute(cache, by, as_of)
    today = jobs.today_ist()
    delivery = nse_delivery.recent(today, 5)
    indices = nse_sectors.index_membership()

    # Pass 1: statements and the fields peers are compared on
    full = {}
    for isin, sc in cards.items():
        raw = cache[isin]
        f = {k: {"data": v} for k, v in raw.items() if k != "fetched_at"}
        ind, price = sc["industry"], sc["price"]
        st = statements.analyse(ind, f, price)
        fin = analysis.financials(f)
        prof = raw.get("profile") or {}
        full[isin] = {"f": f, "fin": fin, "st": st, "kr": analysis.key_ratios(f), "sector": prof.get("sector") or sc.get("sector") or sc["industry_label"],
                      "desc": prof.get("company_profile")}

    # Peers: same Upstox sector (basic industry); market share, concentration, medians
    groups = defaultdict(list)
    for isin, x in full.items():
        groups[x["sector"]].append(isin)
    peer_stats = {}
    for sec, members in groups.items():
        rev = {i: (full[i]["st"]["years"][0]["revenue"] if full[i]["st"].get("available") else None) for i in members}
        tot = sum(v for v in rev.values() if v and v > 0)
        ranked = sorted([i for i in members if rev[i] and rev[i] > 0], key=lambda i: -rev[i])
        shares = [rev[i] / tot * 100 for i in ranked] if tot else []
        y0 = lambda i, k: (full[i]["st"]["years"][0].get(k) if full[i]["st"].get("available") else None)  # noqa: E731
        peer_stats[sec] = {
            "n_peers": len(members), "industry_revenue_cr": round(tot) if tot else None, "ranked": ranked,
            "top": [cards[i]["symbol"] for i in ranked[:5]], "top3_share_pct": round(sum(shares[:3]), 1) if shares else None,
            "hhi": round(sum(s * s for s in shares)) if shares else None,
            "median_net_margin": median([y0(i, "net_margin_pct") for i in members]), "median_roe": median([y0(i, "roe_pct") for i in members]),
            "median_asset_turnover": median([y0(i, "asset_turnover") for i in members]),
            "median_revenue_cagr": median([full[i]["st"].get("cagr", {}).get("revenue_pct") for i in members if full[i]["st"].get("available")]),
            "median_pe": median([cards[i]["metrics"]["pe"] for i in members if (cards[i]["metrics"]["pe"] or 0) > 0]),
            "median_pb": median([cards[i]["metrics"]["pb"] for i in members]), "median_ev_ebitda": median([cards[i]["metrics"]["ev_ebitda"] for i in members if (cards[i]["metrics"]["ev_ebitda"] or 0) > 0]),
            "median_cfo_to_pat": median([y0(i, "cfo_to_pat") for i in members]),
        }
        peer_stats[sec]["revenue"] = rev

    # Pass 2: assemble each card
    out = {}
    for isin, sc in cards.items():
        x = full[isin]
        f, fin, st, kr = x["f"], x["fin"], x["st"], x["kr"]
        ind, price = sc["industry"], sc["price"]
        ps = peer_stats[x["sector"]]
        rev = ps["revenue"].get(isin)
        sh = analysis.shareholding(f) if (f.get("holdings") or {}).get("data") else {}
        prom = sc["metrics"].get("promoter_pct")
        quarterly = {k: [{"period": p, "value": v} for p, v in sorted(vv.items(), key=lambda kv: analysis.period_end(kv[0]) or 0, reverse=True)][:4]
                     for k, vv in analysis._table(((f.get("income_q") or {}).get("data") or {}).get("income_statement"), "category").items()}
        vm = valuation_methods.assess(ind, fin, kr, price, None, quarterly) if fin["periods"] else {}
        divs = [d for d in ((f.get("actions") or {}).get("data") or []) if d.get("name") == "Dividend"]
        c = {
            **sc,
            "profile": {"description": x["desc"], "sector": x["sector"]},
            "st": {k: v for k, v in st.items() if k not in ("years", "source", "not_in_feed")} | {
                "years": [{k: y.get(k) for k in KEEP_YEAR} for y in st.get("years", [])]} if st.get("available") else st,
            "vm": {k: v for k, v in vm.items() if k != "guide"} | {"guide": {k: vm["guide"][k] for k in ("kind", "primary", "avoid", "why")}} if vm else None,
            "dcf": analysis.dcf(ind, fin, kr, price) if fin["periods"] else None,
            "graham_full": analysis.graham(ind, fin, f, price) if fin["periods"] else [],
            "proj": projection(fin) if fin["periods"] else {"available": False},
            "sh": {"periods": sh.get("periods"), "rows": [{"key": r["key"], "values": [{"pct": v["pct"]} for v in r["values"]]} for r in sh.get("rows", [])],
                   "change_over_period": sh.get("change_over_period")} if sh else None,
            "q": quarterly,
            "peer": {k: v for k, v in ps.items() if k not in ("ranked", "revenue")} | {
                "revenue_share_pct": round(rev / ps["industry_revenue_cr"] * 100, 2) if rev and rev > 0 and ps["industry_revenue_cr"] else None,
                "revenue_rank": ps["ranked"].index(isin) + 1 if isin in ps["ranked"] else None},
            "free_float_pct": round(100 - prom, 2) if prom is not None else None,
            "indices": indices.get(isin, []),
            "delivery": nse_delivery.summary(sc["symbol"], delivery),
            "div": {"amount": divs[0].get("amount"), "date": divs[0].get("expiry_date")} if divs else None,
            "hist_mult": {"pe_sector": sc["metrics"].get("pe_sector"), "pb_sector": sc["metrics"].get("pb_sector")},
        }
        c["checklist"] = checklist.build(c)
        c["profile"]["description"] = (x["desc"] or "")[:700] or None
        out[isin] = _round(c)

    # Group into documents under the database's 256 KiB limit: gzip + base64 per document, decompressed by the page
    write_chunks(out, cards, summary, Path(a.out) / "fund", a.chunk_kb)


def _z(obj) -> str:
    return base64.b64encode(gzip.compress(json.dumps(obj, separators=(",", ":"), default=str).encode(), 9)).decode()


def write_chunks(out: dict, cards: dict, summary: dict, od: Path, chunk_kb: int) -> None:
    od.mkdir(parents=True, exist_ok=True)
    for old in od.glob("*.json"):
        old.unlink()
    zs = {i: len(gzip.compress(json.dumps(c, separators=(",", ":"), default=str).encode(), 6)) for i, c in out.items()}
    n = max(1, int(sum(zs.values()) * 1.37 / (chunk_kb * 1024 * 0.75)) + 1)
    while True:
        groups = defaultdict(dict)
        for i in out:
            groups[bucket(i, n)][i] = out[i]
        blobs = {k: _z(g) for k, g in groups.items()}
        if max(len(b) for b in blobs.values()) <= chunk_kb * 1024:
            break
        n += max(1, n // 8)
    for k, b in blobs.items():
        (od / f"c{k:03d}.json").write_text(json.dumps({"z": b, "n": len(groups[k])}))
    # Index for the Investing tab: one compact row per company
    keep = ("isin", "symbol", "name", "industry", "industry_label", "grade", "composite", "rank", "scores", "metrics", "magic_formula", "graham", "price")
    rows = [{k: c.get(k) for k in keep} for c in cards.values()]
    parts, cur = [], []
    for r in rows:
        cur.append(r)
        if len(cur) >= 1200:
            parts.append(cur)
            cur = []
    if cur:
        parts.append(cur)
    idx = [_z(p) for p in parts]
    while max(len(b) for b in idx) > chunk_kb * 1024:  # split further if needed
        parts = [h for p in parts for h in (p[: len(p) // 2], p[len(p) // 2:])]
        idx = [_z(p) for p in parts]
    for k, b in enumerate(idx):
        (od / f"i{k:02d}.json").write_text(json.dumps({"z": b, "n": len(parts[k])}))
    meta = {**summary, "chunks": n, "index_docs": len(idx), "hash": "fnv1a32(isin) % chunks",
            "companies_with_statements": sum(1 for c in out.values() if (c.get("st") or {}).get("available")),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (od / "meta.json").write_text(json.dumps(meta))
    total = sum(len(b) for b in blobs.values()) + sum(len(b) for b in idx)
    print(f"{len(out)} cards in {n} documents + {len(idx)} index documents, {total // 1024} KB stored -> {od}")

if __name__ == "__main__":
    main()
