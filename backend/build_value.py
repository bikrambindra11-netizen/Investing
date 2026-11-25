"""Graham and Buffett value for every company with statements, as page-database documents.

Usage: python -m backend.build_value CACHE.json OUT_DIR
Writes OUT_DIR/value/cNNN.json (one card per company, grouped; gzip+base64), OUT_DIR/value/i0.json.. (the
ranking table) and OUT_DIR/value/meta.json."""
import base64
import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import analysis, macro, statements, value_models  # noqa: E402
from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.build_cards import bucket  # noqa: E402

FIN = {"banks", "nbfc", "insurance"}
YEAR_KEYS = ["period", "revenue", "pat", "eps", "book_value_per_share", "roe_pct", "net_margin_pct", "cfo", "cfi", "current_ratio", "liabilities_to_equity"]


def z(o) -> str:
    return base64.b64encode(gzip.compress(json.dumps(o, separators=(",", ":"), default=str).encode(), 9)).decode()


def main() -> None:
    cache_path, out = Path(sys.argv[1]), Path(sys.argv[2]) / "value"
    init_db()
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    by = {r["isin"]: r for r in rows}
    cache = json.loads(cache_path.read_text())
    pts = macro._points("india_10y")
    bond = pts[-1][1] if pts else None
    labels = {k: v["label"] for k, v in macro.load_industries().items()}
    cards, index = {}, []
    for isin, raw in cache.items():
        r = by.get(isin)
        if not r or not (raw.get("income") or raw.get("balance")):
            continue
        f = {k: {"data": v} for k, v in raw.items() if k != "fetched_at"}
        ys = statements.years(f)
        if not ys:
            continue
        prof = raw.get("profile") or {}
        ind = macro.resolve_industry(prof.get("sector"), r["name"], r.get("sector"))
        fin = analysis.financials(f)
        price = r["close"]
        kr = analysis.key_ratios(f)
        v = value_models.value(ys, price, bond, ind in FIN, analysis.graham(ind, fin, f, price) if fin["periods"] else [],
                               pe=(kr.get("P/E") or {}).get("company"), pb=(kr.get("P/B") or {}).get("company"), industry=ind)
        if v.get("available"):
            eve = (kr.get("EV/EBITDA") or {}).get("company")
            v["magic"]["earnings_yield_pct"] = round(100 / eve, 1) if eve and eve > 0 else None
        if not v.get("available"):
            continue
        c = {"isin": isin, "symbol": r["symbol"], "name": r["name"], "industry": labels.get(ind, ind), "industry_id": ind, "sector": prof.get("sector"),
             "price": price, "price_date": str(r["price_date"]), "v": v, "years": [{k: y.get(k) for k in YEAR_KEYS} for y in ys],
             "fetched_at": raw.get("fetched_at")}
        cards[isin] = c
        g, b = v["graham"], v["buffett"]
        index.append([isin, r["symbol"], r["name"], labels.get(ind, ind), price, g["number"], g["formula"], b["value"], v.get("value_mid"),
                      v.get("margin_of_safety_pct"), g["passed"], g["of"], b["passed"], b["of"], round((r["turnover"] or 0) / 1e7, 1), 1 if v.get("suspect") else 0])
    # Greenblatt: rank on return on capital and on earnings yield, add the ranks, lowest total = best
    elig = [i for i, c in cards.items() if not c["v"]["magic"]["excluded"] and c["v"]["magic"]["roc_pct"] is not None
            and c["v"]["magic"].get("earnings_yield_pct") and (by[i]["turnover"] or 0) >= 1e7 and not c["v"].get("suspect")]
    r1 = {i: k for k, i in enumerate(sorted(elig, key=lambda i: -cards[i]["v"]["magic"]["roc_pct"]), 1)}
    r2 = {i: k for k, i in enumerate(sorted(elig, key=lambda i: -cards[i]["v"]["magic"]["earnings_yield_pct"]), 1)}
    for pos, i in enumerate(sorted(elig, key=lambda i: (r1[i] + r2[i], r1[i])), 1):
        cards[i]["v"]["magic"].update(rank=pos, of=len(elig), roc_rank=r1[i], ey_rank=r2[i])
    mf = {i: cards[i]["v"]["magic"] for i in cards}
    index = [row + [mf[row[0]].get("rank"), mf[row[0]].get("roc_pct"), mf[row[0]].get("earnings_yield_pct")] for row in index]
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    n = max(1, len(cards) // 120 + 1)
    groups = defaultdict(dict)
    for i, c in cards.items():
        groups[bucket(i, n)][i] = c
    for k in range(n):
        (out / f"c{k:03d}.json").write_text(json.dumps({"z": z(groups.get(k, {}))}))
    parts = [index[i:i + 2500] for i in range(0, len(index), 2500)] or [[]]
    for k, p in enumerate(parts):
        (out / f"i{k}.json").write_text(json.dumps({"z": z(p)}))
    meta = {"chunks": n, "index_parts": len(parts), "companies": len(cards), "bond_yield": bond, "bond_yield_date": pts[-1][0] if pts else None,
            "prices_as_of": as_of, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "columns": ["isin", "symbol", "name", "industry", "price", "graham_number", "graham_formula", "buffett_value", "value_mid",
                        "margin_of_safety_pct", "graham_passed", "graham_of", "buffett_passed", "buffett_of", "turnover_cr", "flagged", "mf_rank", "roc_pct", "earnings_yield_pct"],
            "magic_formula_universe": len(elig)}
    (out / "meta.json").write_text(json.dumps(meta, default=str))
    sizes = [os.path.getsize(p) for p in out.glob("*.json")]
    print(f"{len(cards)} companies valued, {n} card documents (largest {max(sizes) // 1024} KB), {len(parts)} index documents")


if __name__ == "__main__":
    main()
