"""Live, on-demand analysis of one stock: fresh data from every source, all numeric parts of the
analysis framework, a rating, and Greenblatt's Magic Formula measures. Writes one JSON file.

Usage: python -m backend.analyze_stock ISIN OUT.json
Needs the Upstox Analytics Token (sent by the network proxy) for company financials.
"""
import json
import os
import sys
from datetime import datetime, timezone

os.environ.setdefault("RUN_JOBS", "false")
os.environ.setdefault("UPSTOX_ACCESS_TOKEN", "proxy-injected")  # the proxy replaces it with the real token

from backend.app import analysis, jobs, macro  # noqa: E402
from backend.app.db import Instrument, SessionLocal, init_db  # noqa: E402
from backend.sources import upstox_bulk, upstox_fundamentals  # noqa: E402

FINANCIAL = {"banks", "nbfc"}
EXCLUDED_FROM_MAGIC_FORMULA = FINANCIAL | {"power"}  # Greenblatt leaves out financials and utilities


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def projection(fin: dict) -> dict:
    """Simple 2-year trend projection from the last few years' growth (not a forecast)."""
    rows = [r for r in fin["periods"] if r["revenue"] is not None]
    g = fin["growth"]
    rg, pg = g.get("revenue_cagr_pct"), g.get("net_profit_cagr_pct")
    if not rows or rg is None:
        return {"available": False}
    rg = clamp(rg, -10, 25)
    pg = clamp(pg if pg is not None else rg, -15, 30)
    base = rows[0]
    eps_row = analysis.latest_with(rows, "eps")
    yr = int(base["period"][-4:])
    out = []
    for n in (1, 2, 3):
        out.append({"period": f"{base['period'][:3]} {yr + n} (projected)",
                    "revenue": round(base["revenue"] * (1 + rg / 100) ** n),
                    "net_profit": round(base["net_profit"] * (1 + pg / 100) ** n) if base["net_profit"] else None,
                    "eps": round(eps_row["eps"] * (1 + pg / 100) ** (n + (yr - int(eps_row["period"][-4:]))), 2)
                    if eps_row else None})
    return {"available": True, "revenue_growth_pct": rg, "profit_growth_pct": pg, "years": out,
            "method": f"Revenue grows {rg}% and profit {pg}% a year, the recent trend capped to a realistic range."}


def intrinsic_value(industry: str, fin: dict, val: dict | None, proj: dict, price: float | None) -> dict:
    """Fair value from projected earnings (or book value for lenders) and a sensible multiple."""
    if not val or not proj.get("available"):
        return {"available": False, "reason": "Not enough financial data."}
    m = {x["name"]: x for x in val["metrics"]}
    pe_hist = [h["pe"] for h in val["history"] if h["pe"]]
    pb_hist = [h["pb"] for h in val["history"] if h["pb"]]
    discount = 1.12 ** 2  # bring a value two years out back to today at 12% a year
    if industry in FINANCIAL and pb_hist:
        latest = analysis.latest_with(fin["periods"], "eps", "equity", "net_profit")
        if not latest:
            return {"available": False, "reason": "Book value not available."}
        bvps = latest["equity"] / (latest["net_profit"] / latest["eps"])
        mult = min(sum(pb_hist) / len(pb_hist), (m.get("P/B") or {}).get("sector") or 99)
        g = proj["profit_growth_pct"] / 100
        value = bvps * (1 + g) ** 2 * mult / discount
        method = f"Book value per share ₹{bvps:.0f}, grown 2 years with profits, × P/B {mult:.2f} (lower of own average and sector), discounted at 12% a year."
    else:
        eps2 = proj["years"][1]["eps"]
        if not eps2 or eps2 <= 0:
            return {"available": False, "reason": "Earnings are negative, so an earnings-based value is not meaningful."}
        own = sum(pe_hist) / len(pe_hist) if pe_hist else None
        sector = (m.get("P/E") or {}).get("sector") or (val.get("all_ratios", {}).get("P/E") or {}).get("sector")
        cands = [x for x in (own, sector) if x and x > 0]
        if not cands:
            return {"available": False, "reason": "No reference P/E available."}
        mult = min(min(cands), 40)
        value = eps2 * mult / discount
        method = f"Projected EPS in 2 years ₹{eps2:.2f} × P/E {mult:.1f} (lower of own average and sector, capped at 40), discounted at 12% a year."
    out = {"available": True, "value": round(value, 2), "low": round(value * 0.85, 2), "high": round(value * 1.15, 2),
           "method": method}
    if price:
        out["upside_pct"] = round((value / price - 1) * 100, 1)
    return out


def magic_formula(industry: str, kr: dict, peers: list[dict]) -> dict:
    """Greenblatt: high return on capital + high earnings yield. Uses ROCE and 1 / (EV/EBITDA)."""
    if industry in EXCLUDED_FROM_MAGIC_FORMULA:
        return {"applies": False, "reason": "Greenblatt leaves out banks, finance companies and utilities: their "
                                            "debt is raw material, so return on capital and EV are not comparable."}
    roc = (kr.get("ROCE") or {}).get("company")
    ev = (kr.get("EV/EBITDA") or {}).get("company")
    if roc is None or not ev or ev <= 0:
        return {"applies": True, "available": False, "reason": "ROCE or EV/EBITDA not available (or EBITDA negative)."}
    ey = round(100 / ev, 2)
    group = [(p["symbol"], p["roce"], 100 / p["ev_ebitda"]) for p in peers if p.get("roce") is not None and p.get("ev_ebitda") and p["ev_ebitda"] > 0]
    me = next((g for g in group if g[1] == roc and abs(g[2] - ey) < 0.01), None)
    if me is None:
        group.append(("this stock", roc, ey))
    by_roc = sorted(group, key=lambda g: -g[1])
    by_ey = sorted(group, key=lambda g: -g[2])
    combined = sorted(group, key=lambda g: by_roc.index(g) + by_ey.index(g))
    target = me or ("this stock", roc, ey)
    pos = combined.index(target) + 1
    good_roc, good_ey = roc >= 20, ey >= 8
    verdict = ("passes Greenblatt's test: a good business at a cheap price" if good_roc and good_ey else
               "good business, but not cheap" if good_roc else
               "cheap, but not a high-return business" if good_ey else
               "fails Greenblatt's test: neither high return on capital nor cheap")
    return {"applies": True, "available": True, "roc_pct": roc, "earnings_yield_pct": ey, "peer_rank": pos,
            "peer_count": len(group), "verdict": verdict,
            "note": "Return on capital = ROCE; earnings yield = 1 ÷ (EV/EBITDA). Greenblatt ranks all companies on both and buys the best combined ranks. "
                    "Here the stock is ranked against its competitors; rules of thumb: return on capital ≥ 20% and earnings yield ≥ 8%."}


def rating(parts: dict) -> dict:
    """Weighted 0-100 score from the numeric parts; research can move it by at most ±10."""
    weights = {"business_quality": 30, "valuation": 20, "graham": 15, "magic_formula": 15, "economy": 10, "price_trend": 10}
    have = {k: v for k, v in parts.items() if v.get("score") is not None}
    total = sum(weights[k] for k in have)
    score = round(sum(weights[k] * have[k]["score"] for k in have) / total * 100) if total else None
    grade = None if score is None else "A" if score >= 75 else "B" if score >= 60 else "C" if score >= 45 else "D" if score >= 30 else "E"
    words = {"A": "Strong", "B": "Good", "C": "Average", "D": "Weak", "E": "Poor"}
    return {"score": score, "grade": grade, "label": words.get(grade), "weights": weights, "parts": parts,
            "note": "Numbers-only score. The research step may adjust it by up to 10 points for management quality and capital allocation."}


def main() -> None:
    isin, out_path = sys.argv[1].upper(), sys.argv[2]
    init_db()
    jobs.refresh_instruments()
    jobs.refresh_sectors()
    jobs.refresh_prices()
    with SessionLocal() as s:
        ins = s.query(Instrument).filter(Instrument.isin == isin).all()
    if not ins:
        raise SystemExit(f"ISIN {isin} not found in the NSE/BSE equity list")
    primary = sorted(ins, key=lambda i: i.exchange != "NSE")[0]

    # Economy data for this company's industry only (fast)
    f = upstox_fundamentals.fetch_all(isin, "proxy-injected")
    sector = ((f.get("profile") or {}).get("data") or {}).get("sector")
    ind = macro.resolve_industry(sector, primary.name, next((i.sector for i in ins if i.sector), None))
    needed = {d["series"] for d in macro.load_industries()[ind]["drivers"]}
    macro.refresh_macro(jobs.today_ist(), only=needed)

    from backend.app import stock  # after data is loaded
    page = stock.stock_page(isin)
    ltp = upstox_bulk.last_prices([primary.instrument_key]).get(primary.instrument_key)
    price = ltp or page["quote"]["close"]
    industry = page["classification"]["industry_id"]
    fin = page["financials"]
    kr = analysis.key_ratios(f)
    proj = projection(fin) if fin else {"available": False}
    iv = intrinsic_value(industry, fin, page["valuation"], proj, price) if fin else {"available": False}
    mf = magic_formula(industry, kr, page["peers"])

    q, g, v, m, st = page["quality"], page["graham"] or [], page["valuation"], page["macro"], page["stats"]
    g_judged = [c for c in g if c["status"] in ("pass", "fail", "partial")]
    parts = {
        "business_quality": {"score": (q["passed"] / q["total"]) if q and q["total"] else None,
                             "note": f"{q['passed']} of {q['total']} quality checks passed" if q else "no financials"},
        "valuation": {"score": {"cheap": 1.0, "fair": 0.6, "expensive": 0.2}.get(v["label"]) if v else None,
                      "note": f"looks {v['label']}" if v else "not available"},
        "graham": {"score": (sum(c["status"] == "pass" for c in g_judged) + 0.5 * sum(c["status"] == "partial" for c in g_judged)) / len(g_judged) if g_judged else None,
                   "note": f"{sum(c['status'] == 'pass' for c in g_judged)} passed, {sum(c['status'] == 'partial' for c in g_judged)} partial of {len(g_judged)}"},
        "magic_formula": {"score": (1 - (mf["peer_rank"] - 1) / max(mf["peer_count"] - 1, 1)) if mf.get("available") else None,
                          "note": f"rank {mf['peer_rank']} of {mf['peer_count']} vs competitors" if mf.get("available") else mf.get("reason", "")},
        "economy": {"score": m["score"]["share_tailwinds"], "note": f"{m['score']['tailwinds']} of {m['score']['judged']} drivers are tailwinds"},
        "price_trend": {"score": clamp(0.5 + (st.get("return_1y") or 0) / 100, 0, 1) if st.get("available") and st.get("return_1y") is not None else None,
                        "note": f"{st.get('return_1y')}% over 1 year" if st.get("available") else "not available"},
    }

    page.pop("candles", None)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "isin": isin, "symbol": primary.symbol, "name": primary.name,
        "live_price": {"price": price, "source": "Upstox market quote" if ltp else page["quote"]["price_source"],
                       "at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        **page,
        "projection": proj, "intrinsic_value": iv, "magic_formula": mf, "rating": rating(parts),
    }
    with open(out_path, "w") as fh:
        json.dump(result, fh, default=str)
    print(f"wrote {out_path}: {result['symbol']} rating {result['rating']['grade']} ({result['rating']['score']}),"
          f" financials {'yes' if fin else 'no'}, size {os.path.getsize(out_path) // 1024} KB")


if __name__ == "__main__":
    main()
