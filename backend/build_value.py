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

from backend.app import analysis, macro, statements, valuation_methods, value_models  # noqa: E402
from backend.app.db import SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.build_cards import bucket  # noqa: E402

FIN = {"banks", "nbfc", "insurance"}

# Valuation and quality ratios, computed for every company. hi = higher is better.
METRICS = {
    "pe": {"label": "P/E", "hi": False, "fmt": "x"},
    "pe_norm": {"label": "P/E on 3-yr average earnings", "hi": False, "fmt": "x"},
    "peg": {"label": "PEG (P/E ÷ profit growth)", "hi": False, "fmt": "x"},
    "pb": {"label": "P/B", "hi": False, "fmt": "x"},
    "pb_vs_roe": {"label": "P/B ÷ justified P/B (from ROE)", "hi": False, "fmt": "x"},
    "ev_ebitda": {"label": "EV/EBITDA", "hi": False, "fmt": "x"},
    "ev_ebitda_mid": {"label": "EV/EBITDA on cycle-average profit", "hi": False, "fmt": "x"},
    "ps": {"label": "Price/sales", "hi": False, "fmt": "x"},
    "p_cfo": {"label": "Price ÷ operating cash flow", "hi": False, "fmt": "x"},
    "fcf_yield": {"label": "Free-cash-flow yield", "hi": True, "fmt": "%"},
    "dcf_upside": {"label": "DCF (Buffett) upside", "hi": True, "fmt": "%"},
    "roe": {"label": "Return on equity", "hi": True, "fmt": "%"},
    "roa": {"label": "Return on assets", "hi": True, "fmt": "%"},
    "roc": {"label": "Return on capital", "hi": True, "fmt": "%"},
    "ey": {"label": "Earnings yield (Greenblatt)", "hi": True, "fmt": "%"},
}

# The ratios that fit each sector, with why, and the ones that mislead there.
FIT = {
    "banks": (["pb_vs_roe", "pb", "roe", "roa", "pe"], "Lenders: book value is the asset base, so P/B judged against return on equity is the core measure (a bank earning more on its book deserves a higher P/B); ROA shows asset quality and leverage; P/E is a cross-check.",
              ["EV/EBITDA and cash-flow DCF: deposits are a bank's raw material, not debt", "Price/sales: interest income is not comparable to sales"]),
    "nbfc": (["pb_vs_roe", "pb", "roe", "roa", "pe"], "Lenders: P/B against return on equity, plus ROA and P/E.",
             ["EV/EBITDA and cash-flow DCF: borrowing is the business itself"]),
    "insurance": (["pb", "roe", "pe_norm"], "Insurers: book value and return on equity (embedded value is not in the data feed); P/E on average earnings as a cross-check.",
                  ["P/E on one year: new policies depress early profit", "EV/EBITDA: policyholder money is not debt"]),
    "it": (["pe", "peg", "fcf_yield", "dcf_upside", "roc"], "Asset-light, cash-rich: earnings and cash flow drive value, so P/E with growth (PEG), free-cash-flow yield and a DCF; return on capital shows quality.",
           ["P/B: the assets are people and client relationships, not on the balance sheet"]),
    "fmcg": (["dcf_upside", "peg", "fcf_yield", "pe", "roc"], "Brand businesses with steady, predictable cash flow: a DCF of owner earnings is the main measure (Buffett), with PEG and free-cash-flow yield; P/E alone always looks high for these.",
             ["P/B: brand value is not on the balance sheet"]),
    "pharma": (["pe", "peg", "ev_ebitda", "roc"], "Product- and approval-driven: P/E against growth, EV/EBITDA to compare companies with different debt, and return on capital.",
               ["P/B: research and approvals are not on the balance sheet"]),
    "consumer_durables": (["pe", "peg", "roc", "fcf_yield"], "Brand-led growers: P/E with growth, return on capital and cash conversion.",
                          ["P/B: brands matter more than assets"]),
    "capital_goods": (["pe", "peg", "p_cfo", "roc"], "Order-book driven and working-capital heavy: P/E with growth, and price ÷ operating cash flow to catch profit tied up in receivables; return on capital.",
                      ["P/B: value lies in engineering skill and the order book"]),
    "metals": (["ev_ebitda_mid", "pb", "pe_norm"], "Asset-heavy, deep cyclical: EV/EBITDA on cycle-average profit and P/B (what the plants are worth), with P/E on average earnings; never current P/E.",
               ["P/E on current earnings: lowest at the peak (Lynch)", "DCF on recent growth: extrapolates a boom or a slump"]),
    "cement": (["ev_ebitda_mid", "pb", "pe_norm"], "Asset-heavy and cyclical: EV/EBITDA on cycle-average profit, P/B as the nearest measure of replacement cost (capacity is not in the data feed), and P/E on average earnings.",
               ["P/E on current earnings: fuel costs and prices swing profit"]),
    "oil_gas": (["ev_ebitda_mid", "pb", "fcf_yield"], "Commodity-driven and asset-heavy: EV/EBITDA on cycle-average profit, P/B, and free-cash-flow yield.",
                ["P/E on one year: crude and refining margins swing profit"]),
    "chemicals": (["ev_ebitda_mid", "peg", "roc"], "Commodity makers are cyclical (cycle-average EV/EBITDA), specialty makers grow (PEG); return on capital separates the two.",
                  ["Valuing a commodity maker like a specialty one"]),
    "textiles": (["pb", "pe_norm", "ev_ebitda_mid"], "Cyclical, asset-heavy, raw-material driven: P/B, P/E on average earnings, cycle-average EV/EBITDA.",
                 ["P/E on one year: cotton prices and export orders swing margins"]),
    "auto": (["pe_norm", "ev_ebitda_mid", "roc"], "Cyclical demand: P/E on average earnings and cycle-average EV/EBITDA, with return on capital.",
             ["P/E on peak earnings (Lynch)"]),
    "power": (["pb_vs_roe", "roe", "ev_ebitda"], "Regulated returns on book value: P/B against return on equity, ROE, and EV/EBITDA for the debt-heavy asset base.",
              ["PEG: growth comes from adding capacity, not margins"]),
    "realty": (["pb", "pe_norm", "p_cfo"], "Asset-based: P/B (land and projects; NAV is not in the data feed), P/E on average earnings, and price ÷ operating cash flow because reported profit is booked only on handover.",
               ["P/E on one year: profit is lumpy"]),
    "gold": (["pe", "peg", "p_cfo", "roc"], "Branded jewellers are inventory-heavy growers: P/E with growth, price ÷ operating cash flow (inventory eats cash), return on capital.",
             ["P/B: brand and stores drive value"]),
    "capital_markets": (["pe_norm", "roe", "fcf_yield"], "Fee businesses on little capital whose earnings rise and fall with markets: P/E on average earnings, ROE, free-cash-flow yield.",
                        ["P/B: these businesses need almost no capital"]),
    "general": (["pe", "ev_ebitda", "fcf_yield", "roc"], "Mixed businesses: P/E, EV/EBITDA to compare different debt levels, free-cash-flow yield and return on capital.", []),
}


# Only businesses whose earnings follow a commodity price have a cycle. (Upstox sector words, name words) -> (commodity, price series of what they sell)
COMMODITY = [
    (["zinc"], [], ("zinc", ["zinc"])),
    ([], ["hindustan zinc"], ("zinc", ["zinc"])),
    ([], ["hindustan copper"], ("copper", ["copper"])),
    (["copper"], [], ("copper", ["copper"])),
    ([], ["national aluminium", "hindalco", "vedanta"], ("aluminium", ["aluminium"])),
    (["aluminium"], [], ("aluminium", ["aluminium"])),
    (["non ferrous"], [], ("non-ferrous metals", ["aluminium", "zinc", "copper"])),
    ([], ["nmdc", "iron ore", "kiocl", "sandur"], ("iron ore", ["iron_ore"])),
    ([], ["coal india", "coal"], ("coal", ["coal"])),
    (["ferro"], [], ("ferro alloys / steel", ["iron_ore"])),
    (["steel"], [], ("steel", ["iron_ore"])),
    (["mining", "minerals"], [], ("minerals", ["iron_ore", "coal"])),
    (["oil exploration", "crude oil"], [], ("crude oil", ["brent"])),
    (["refiner"], [], ("refining (crude-linked)", [])),
    (["petrochemical"], [], ("petrochemicals (crude-linked)", [])),
    (["cement"], [], ("cement", [])),
    (["construction material"], [], ("cement", [])),
    (["sugar"], [], ("sugar", [])),
    (["paper"], [], ("paper", [])),
]


def commodity_of(sector: str | None, name: str | None) -> tuple[str, list[str]] | None:
    sec, nm = (sector or "").lower(), f" {(name or '').lower()} "
    if any(w in sec for w in ("steel & iron products",)) and any(w in nm for w in (" tube", " pipe", "apollo")):
        return None  # pipe and tube makers process steel; their margin is a spread, not the steel cycle
    for sec_words, name_words, out in COMMODITY:
        if (sec_words and any(w in sec for w in sec_words)) or (name_words and any(w in nm for w in name_words)):
            return out
    return None


def metrics(ys: list[dict], fin: dict, kr: dict, price: float | None, v: dict) -> dict:
    """Every ratio in METRICS for one company (None where it cannot be computed)."""
    r = lambda x, n=2: None if x is None else round(x, n)  # noqa: E731
    y = ys[0]
    pe = (kr.get("PE") or kr.get("P/E") or {}).get("company")
    pb = (kr.get("P/B") or {}).get("company")
    eve = (kr.get("EV/EBITDA") or {}).get("company")
    inp = v.get("inputs", {})
    eps_n = inp.get("normal EPS ₹ (3-yr average profit)")
    bvps = inp.get("book value per share ₹ (price ÷ P/B)")
    shares = (y["equity"] / bvps) if y.get("equity") and bvps else y.get("shares_cr")
    mcap = price * shares if price and shares else None
    g = inp.get(f"profit growth a year ({len(ys) - 1} yrs)")
    roe = y.get("roe_pct")
    cfo = [x["cfo"] for x in ys[:3] if x.get("cfo") is not None]
    fcf = [x["cfo"] + x["cfi"] for x in ys[:4] if x.get("cfo") is not None and x.get("cfi") is not None]
    ops = [p["operating_profit"] for p in fin.get("periods", []) if p.get("operating_profit") is not None]
    ke, gl = 12.5, 5.0
    jpb = (roe - gl) / (ke - gl) if roe and roe > gl else None
    m = {
        "pe": r(pe, 1) if pe and pe > 0 else None,
        "pe_norm": r(price / eps_n, 1) if price and eps_n and eps_n > 0 else None,
        "peg": r(pe / g, 2) if pe and pe > 0 and g and g > 0 else None,
        "pb": r(pb), "pb_vs_roe": r(pb / jpb) if pb and jpb else None,
        "ev_ebitda": r(eve, 1) if eve and eve > 0 else None,
        "ev_ebitda_mid": r(eve * ops[0] / (sum(ops) / len(ops)), 1) if eve and eve > 0 and ops and ops[0] and ops[0] > 0 and sum(ops) > 0 else None,
        "ps": r(mcap / y["revenue"]) if mcap and y.get("revenue") else None,
        "p_cfo": r(mcap / (sum(cfo) / len(cfo)), 1) if mcap and cfo and sum(cfo) > 0 else None,
        "fcf_yield": r(sum(fcf) / len(fcf) / mcap * 100, 1) if mcap and fcf else None,
        "dcf_upside": r((v["buffett"]["value"] / price - 1) * 100, 1) if v.get("buffett", {}).get("value") and price else None,
        "roe": r(roe, 1), "roa": r(y.get("roa_pct"), 1),
        "roc": (v.get("magic") or {}).get("roc_pct"),
        "ey": (v.get("magic") or {}).get("earnings_yield_pct"),
    }
    return m


# How each sector's companies are ranked: the measures that fit the industry (each ranked within the sector,
# ranks added, lowest total first). mos = margin of safety on the Graham/Buffett values that suit the industry;
# roc / ey = Greenblatt's return on capital and earnings yield; roe = return on equity; cycle = earlier in the
# cycle ranks better (Graham and Lynch: buy cyclicals on depressed, not peak, earnings).
_GREEN = "Greenblatt's Magic Formula (return on capital + earnings yield) works here, combined with the Graham/Buffett margin of safety."
SECTORS = {
    "it": {"factors": ["roc", "ey", "mos"], "why": "Asset-light, cash-rich: " + _GREEN},
    "fmcg": {"factors": ["roc", "ey", "mos"], "why": "Brand businesses with high returns on capital: " + _GREEN},
    "pharma": {"factors": ["roc", "ey", "mos"], "why": _GREEN},
    "consumer_durables": {"factors": ["roc", "ey", "mos"], "why": _GREEN},
    "gold": {"factors": ["roc", "ey", "mos"], "why": _GREEN},
    "capital_markets": {"factors": ["roc", "ey", "mos"], "why": "Fee businesses on little capital: " + _GREEN},
    "general": {"factors": ["roc", "ey", "mos"], "why": _GREEN},
    "capital_goods": {"factors": ["roc", "ey", "mos"], "why": "Order-book driven: Magic Formula plus margin of safety."},
    "chemicals": {"factors": ["ey", "mos", "roc", "cycle"], "why": "Partly cyclical: Magic Formula and margin of safety on cycle-average earnings; earlier in the cycle ranks better."},
    "auto": {"factors": ["ey", "mos", "roc"], "why": "Cyclical demand: Magic Formula and margin of safety on cycle-average earnings; earlier in the cycle ranks better."},
    "metals": {"factors": ["mos", "ey", "cycle"], "why": "Deep cyclical (The Intelligent Investor; Lynch): value on cycle-average earnings and assets, and earlier in the cycle ranks better; return on capital is ignored because it peaks with prices."},
    "cement": {"factors": ["mos", "ey", "cycle"], "why": "Cyclical and asset-heavy: Graham margin of safety on assets and cycle-average earnings, earnings yield, and earlier in the cycle ranks better."},
    "oil_gas": {"factors": ["mos", "ey", "cycle"], "why": "Commodity-driven: margin of safety on assets and cycle-average cash flow, earnings yield, and earlier in the cycle ranks better."},
    "textiles": {"factors": ["mos", "ey"], "why": "Cyclical, raw-material driven: margin of safety, earnings yield, and earlier in the cycle ranks better."},
    "realty": {"factors": ["mos"], "why": "Asset-based and cyclical: Graham's book-value margin of safety, and earlier in the cycle ranks better; the Magic Formula does not fit lumpy profits."},
    "banks": {"factors": ["mos", "roe"], "why": "Greenblatt leaves out banks. Graham/Buffett: margin of safety on book value and distributable profit, plus return on equity."},
    "nbfc": {"factors": ["mos", "roe"], "why": "Greenblatt leaves out lenders. Graham/Buffett: margin of safety on book value and distributable profit, plus return on equity."},
    "insurance": {"factors": ["mos", "roe"], "why": "Greenblatt leaves out insurers. Margin of safety on book value and distributable profit, plus return on equity."},
    "power": {"factors": ["mos", "roe"], "why": "Greenblatt leaves out utilities. Regulated returns on book value: Graham margin of safety plus return on equity."},
}
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
        comm = commodity_of(prof.get("sector"), r["name"])
        if v.get("available") and comm:
            q_rows = analysis._table(((f.get("income_q") or {}).get("data") or {}).get("income_statement"), "category")
            quarterly = {k: [{"period": p, "value": x} for p, x in sorted(vv.items(), key=lambda kv: analysis.period_end(kv[0]) or 0, reverse=True)][:4] for k, vv in q_rows.items()}
            cyc = valuation_methods.cycle_position(ind, fin, quarterly, valuation_methods._basics(fin, kr, price), products=comm[1], commodity=comm[0])
            v["cycle"] = {k: cyc.get(k) for k in ("stage", "evidence", "lynch", "note", "how", "commodity")}
        if v.get("available"):
            eve = (kr.get("EV/EBITDA") or {}).get("company")
            v["magic"]["earnings_yield_pct"] = round(100 / eve, 1) if eve and eve > 0 else None
            v["ratios"] = metrics(ys, fin, kr, price, v)
        if not v.get("available"):
            continue
        c = {"isin": isin, "symbol": r["symbol"], "name": r["name"], "industry": labels.get(ind, ind), "industry_id": ind, "sector": prof.get("sector"),
             "price": price, "price_date": str(r["price_date"]), "v": v, "years": [{k: y.get(k) for k in YEAR_KEYS} for y in ys],
             "fetched_at": raw.get("fetched_at")}
        cards[isin] = c
        g, b = v["graham"], v["buffett"]
        index.append([isin, r["symbol"], r["name"], labels.get(ind, ind), price, g["number"], g["formula"], b["value"], v.get("value_mid"),
                      v.get("margin_of_safety_pct"), g["passed"], g["of"], b["passed"], b["of"], round((r["turnover"] or 0) / 1e7, 1), 1 if v.get("suspect") else 0,
                      ind, ys[0].get("roe_pct")])
    # Greenblatt: rank on return on capital and on earnings yield, add the ranks, lowest total = best
    elig = [i for i, c in cards.items() if not c["v"]["magic"]["excluded"] and c["v"]["magic"]["roc_pct"] is not None
            and c["v"]["magic"].get("earnings_yield_pct") and (by[i]["turnover"] or 0) >= 1e7 and not c["v"].get("suspect")]
    r1 = {i: k for k, i in enumerate(sorted(elig, key=lambda i: -cards[i]["v"]["magic"]["roc_pct"]), 1)}
    r2 = {i: k for k, i in enumerate(sorted(elig, key=lambda i: -cards[i]["v"]["magic"]["earnings_yield_pct"]), 1)}
    for pos, i in enumerate(sorted(elig, key=lambda i: (r1[i] + r2[i], r1[i])), 1):
        cards[i]["v"]["magic"].update(rank=pos, of=len(elig), roc_rank=r1[i], ey_rank=r2[i])
    mf = {i: cards[i]["v"]["magic"] for i in cards}
    index = [row + [mf[row[0]].get("roc_pct"), mf[row[0]].get("earnings_yield_pct"),
                    (cards[row[0]]["v"].get("cycle") or {}).get("stage"), mf[row[0]].get("rank"), cards[row[0]]["v"].get("ratios")] for row in index]
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    n = max(1, len(cards) // 120 + 1)
    groups = defaultdict(dict)
    for i, c in cards.items():
        groups[bucket(i, n)][i] = c
    for k in range(n):
        (out / f"c{k:03d}.json").write_text(json.dumps({"z": z(groups.get(k, {}))}))
    parts = [index[i:i + 900] for i in range(0, len(index), 900)] or [[]]
    for k, p in enumerate(parts):
        (out / f"i{k}.json").write_text(json.dumps({"z": z(p)}))
    meta = {"chunks": n, "index_parts": len(parts), "companies": len(cards), "bond_yield": bond, "bond_yield_date": pts[-1][0] if pts else None,
            "prices_as_of": as_of, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "columns": ["isin", "symbol", "name", "industry", "price", "graham_number", "graham_formula", "buffett_value", "value_mid",
                        "margin_of_safety_pct", "graham_passed", "graham_of", "buffett_passed", "buffett_of", "turnover_cr", "flagged", "industry_id", "roe_pct",
                        "roc_pct", "earnings_yield_pct", "cycle", "mf_rank", "ratios"],
            "metrics": METRICS, "fit": {k: {"metrics": a, "why": b, "avoid": c} for k, (a, b, c) in FIT.items()},
            "sectors": SECTORS, "labels": labels,
            "magic_formula_universe": len(elig)}
    (out / "meta.json").write_text(json.dumps(meta, default=str))
    sizes = [os.path.getsize(p) for p in out.glob("*.json")]
    print(f"{len(cards)} companies valued, {n} card documents (largest {max(sizes) // 1024} KB), {len(parts)} index documents")


if __name__ == "__main__":
    main()
