"""Industry-specific valuation: which methods suit an industry (backend/config/valuation_methods.yaml),
where a cyclical company stands in its cycle, and each method worked out with its numbers.

Every result carries the figures used. A method that needs a number we do not have (installed capacity,
embedded value, land NAV) says so instead of guessing."""
from pathlib import Path

import yaml

from . import analysis, macro

CONFIG = Path(__file__).resolve().parent.parent / "config" / "valuation_methods.yaml"
KE = analysis.COST_OF_EQUITY
GT = analysis.TERMINAL_GROWTH

NAMES = {
    "pb_roe": "P/B against return on equity", "residual_income": "Residual income (excess return) value",
    "dcf_earnings": "DCF on earnings", "reverse_dcf": "Reverse DCF (growth the price assumes)",
    "pe_growth": "P/E against profit growth", "normalised_pe": "P/E on cycle-average earnings",
    "mid_cycle_ev_ebitda": "EV/EBITDA on cycle-average profit", "pb_history": "P/B against own history",
    "p_sales": "Price to sales", "ev_replacement": "EV against replacement cost", "p_ev": "Price to embedded value",
    "p_nav": "Price to net asset value", "sotp": "Sum of the parts",
}


def load() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def guide(industry: str) -> dict:
    """The method guide for an industry, with sources written out."""
    cfg = load()
    ind = cfg["industries"].get(industry) or cfg["industries"]["general"]
    return {"industry": industry, "kind": ind["kind"], "cyclical": ind.get("cyclical", False),
            "primary": [{"id": m, "name": NAMES[m]} for m in ind["primary"]],
            "secondary": [{"id": m, "name": NAMES[m]} for m in ind.get("secondary", [])],
            "avoid": ind.get("avoid", []), "why": ind["why"], "watch": ind.get("watch", []),
            "cycle_signals": ind.get("cycle_signals", []),
            "sources": [cfg["sources"][s] for s in ind.get("sources", [])]}


# ------------------------------------------------------------------ basics

def _basics(fin: dict, kr: dict, price: float | None) -> dict:
    rows = fin.get("periods") or []
    latest = rows[0] if rows else {}
    eps = latest.get("eps")
    pat = latest.get("net_profit")
    shares = pat / eps if pat and eps else None  # crore shares
    pb = (kr.get("P/B") or {}).get("company")
    roe = (kr.get("ROE") or {}).get("company") or latest.get("roe_pct")
    bvps = price / pb if price and pb else None
    return {"rows": rows, "latest": latest, "eps": eps, "pat": pat, "shares": shares, "pb": pb, "roe": roe, "bvps": bvps,
            "pe": (kr.get("P/E") or {}).get("company"), "pe_sector": (kr.get("P/E") or {}).get("sector"),
            "ev_ebitda": (kr.get("EV/EBITDA") or {}).get("company"), "ev_ebitda_sector": (kr.get("EV/EBITDA") or {}).get("sector"),
            "pb_sector": (kr.get("P/B") or {}).get("sector"),
            "growth": (fin.get("growth") or {}).get("net_profit_cagr_pct"), "growth_years": (fin.get("growth") or {}).get("years")}


def _vs_price(value: float | None, price: float | None) -> dict:
    if not value or not price:
        return {}
    up = round((value / price - 1) * 100, 1)
    return {"value": round(value, 2), "upside_pct": up,
            "reading": "price below this value" if up > 15 else "price above this value" if up < -15 else "price close to this value"}


def earnings_dcf(pat: float, roe: float, g: float, shares: float) -> float:
    """Per-share value: profit grows at g fading to the long-run rate over 10 years; cash to shareholders
    each year = profit x (1 - growth / ROE); discounted at the cost of equity."""
    ke, gt = KE / 100, GT / 100
    pv, earn = 0.0, pat
    for yr in range(1, 11):
        gi = g + (GT - g) * (yr - 1) / 9
        earn *= 1 + gi / 100
        pv += earn * max(0.0, 1 - gi / roe) / (1 + ke) ** yr
    tv = earn * (1 + gt) * max(0.0, 1 - GT / roe) / (ke - gt) / (1 + ke) ** 10
    return (pv + tv) / shares


# ------------------------------------------------------------------ methods

def m_pb_roe(b, price, **_):
    roe, pb, bvps = b["roe"], b["pb"], b["bvps"]
    if not (roe and pb and bvps):
        return {"available": False, "reason": "Needs P/B and return on equity."}
    g = GT  # the stable-growth formula needs a growth rate the company can keep forever: long-run nominal growth
    just = max(0.0, (roe - g) / (KE - g))
    implied_roe = g + pb * (KE - g)
    return {"available": True, "figures": {"P/B": pb, "ROE %": round(roe, 1), "cost of equity %": KE, "long-run growth %": g,
                                          "justified P/B": round(just, 2), "book value per share": round(bvps, 2),
                                          "ROE the price assumes %": round(implied_roe, 1)},
            "explain": f"A company earning {roe:.1f}% on its book for good, growing {g}% a year, with shareholders asking {KE}%, "
                       f"is worth about {just:.2f}× book; it trades at {pb:.2f}×. Put the other way, today's P/B assumes a lasting ROE of about {implied_roe:.1f}%.",
            **_vs_price(just * bvps, price)}


def m_residual_income(b, price, **_):
    roe, bvps = b["roe"], b["bvps"]
    if not (roe and bvps):
        return {"available": False, "reason": "Needs return on equity and book value."}
    g = max(0.0, min(b["growth"] or GT, 0.8 * roe, 20))
    retain = min(1.0, g / roe) if roe > 0 else 0
    bv, pv, ke = bvps, 0.0, KE / 100
    for yr in range(1, 11):
        roe_t = roe + (KE + 2 - roe) * (yr - 1) / 9 if roe > KE + 2 else roe  # high returns fade toward cost of equity + 2 as competition bites
        pv += (roe_t - KE) / 100 * bv / (1 + ke) ** yr
        bv *= 1 + roe_t / 100 * retain
    value = bvps + pv
    return {"available": True, "figures": {"book value per share": round(bvps, 2), "ROE %": round(roe, 1), "cost of equity %": KE,
                                          "share of profit kept %": round(retain * 100)},
            "explain": f"Book value ₹{bvps:,.2f} plus 10 years of profit earned above the {KE}% shareholders ask for "
                       f"(ROE {roe:.1f}%{' fading toward ' + str(KE + 2) + '%' if roe > KE + 2 else ''}), with no excess return after.",
            **_vs_price(value, price)}


def m_dcf_earnings(b, price, **_):
    roe, pat, shares = b["roe"], b["pat"], b["shares"]
    if not (roe and roe > 0 and pat and pat > 0 and shares):
        return {"available": False, "reason": "Needs positive profit and return on equity."}
    g = max(0.0, min(b["growth"] or 0, 20, 0.8 * roe))
    v = earnings_dcf(pat, roe, g, shares)
    return {"available": True, "figures": {"profit ₹ Cr": round(pat), "ROE %": round(roe, 1), "growth %": round(g, 1),
                                          "discount rate %": KE, "long-run growth %": GT},
            "explain": f"Profit ₹{pat:,.0f} Cr growing {g:.1f}% a year fading to {GT}% over 10 years; cash to shareholders = profit × (1 − growth ÷ ROE); discounted at {KE}%.",
            **_vs_price(v, price)}


def m_reverse_dcf(b, price, **_):
    roe, pat, shares = b["roe"], b["pat"], b["shares"]
    if not (roe and roe > 0 and pat and pat > 0 and shares and price):
        return {"available": False, "reason": "Needs positive profit, return on equity and a price."}
    lo, hi = 0.0, min(0.95 * roe, 60.0)
    if earnings_dcf(pat, roe, hi, shares) < price:
        implied, capped = hi, True
    else:
        capped = False
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if earnings_dcf(pat, roe, mid, shares) < price else (lo, mid)
        implied = (lo + hi) / 2
    hist = b["growth"]
    cmp = ""
    if hist is not None:
        cmp = (f" Its profit actually grew {hist:.1f}% a year over the last {b['growth_years']} years, "
               + ("more than the price needs." if hist > implied + 2 else "less than the price needs." if hist < implied - 2 else "about what the price needs."))
    return {"available": True, "figures": {"growth implied %": round(implied, 1), "past profit growth %": hist, "ROE %": round(roe, 1)},
            "explain": (f"To justify ₹{price:,.2f}, profit must grow about {implied:.1f}% a year for the next decade (fading to {GT}%), with ROE staying near {roe:.0f}%."
                        if not capped else f"Even {implied:.0f}% growth a year does not justify the price at today's ROE.") + cmp,
            "reading": "growth needed by the price: " + (f"more than {implied:.0f}%" if capped else f"{implied:.1f}% a year")}


def m_pe_growth(b, price, **_):
    pe, g = b["pe"], b["growth"]
    if not pe or pe <= 0:
        return {"available": False, "reason": "P/E not meaningful (no profit)."}
    if not g or g <= 0:
        return {"available": True, "figures": {"P/E": pe, "profit growth %": g},
                "explain": f"P/E {pe:.1f} with no profit growth over the period: the price relies on growth returning.", "reading": "no growth to set against P/E"}
    peg = pe / g
    reading = ("P/E well below growth (Lynch: attractive)" if peg <= 0.5 else "P/E below growth" if peg < 1 else
               "P/E about equal to growth (Lynch: fair)" if peg <= 1.3 else "P/E above growth" if peg < 2 else "P/E twice growth or more (Lynch: unattractive)")
    return {"available": True, "figures": {"P/E": pe, "sector P/E": b["pe_sector"], "profit growth % a year": round(g, 1), "years": b["growth_years"], "PEG": round(peg, 2)},
            "explain": f"P/E {pe:.1f} against profit growth of {g:.1f}% a year over {b['growth_years']} years: PEG {peg:.2f}. Lynch: a fairly priced company's P/E roughly equals its growth rate.",
            "reading": reading}


def _avg_eps(rows):
    eps = [r["eps"] for r in rows if r.get("eps") is not None]
    return (sum(eps) / len(eps), len(eps)) if eps else (None, 0)


def m_normalised_pe(b, price, **_):
    avg, n = _avg_eps(b["rows"])
    if not avg or not price:
        return {"available": False, "reason": "Needs EPS history."}
    if avg <= 0:
        return {"available": True, "figures": {"average EPS": round(avg, 2), "years": n}, "explain": "Average earnings across the years are negative.", "reading": "loss-making on average"}
    npe = price / avg
    return {"available": True, "figures": {"P/E on average EPS": round(npe, 1), "average EPS ₹": round(avg, 2), "years averaged": n,
                                          "P/E on latest EPS": b["pe"], "15× average EPS ₹": round(15 * avg, 2)},
            "explain": f"Price ÷ average EPS of the last {n} years = {npe:.1f}. Graham treated about 15–16× average earnings as the most a careful investor should pay"
                       + (" (Upstox gives only these years; Graham and Dodd used 5–10)." if n < 7 else "."),
            "reading": "at or below Graham's 15×" if npe <= 15 else "above Graham's 15×"}


def m_mid_cycle_ev_ebitda(b, price, **_):
    ev_e, rows = b["ev_ebitda"], b["rows"]
    ops = [r["operating_profit"] for r in rows if r.get("operating_profit") is not None]
    latest_op = rows[0].get("operating_profit") if rows else None
    if not ev_e or not ops or not latest_op or latest_op <= 0:
        return {"available": False, "reason": "Needs EV/EBITDA and operating-profit history."}
    avg = sum(ops) / len(ops)
    if avg <= 0:
        return {"available": False, "reason": "Average operating profit is not positive."}
    mid = ev_e * latest_op / avg
    return {"available": True, "figures": {"EV/EBITDA now": ev_e, "EV/EBITDA on average profit": round(mid, 1), "sector EV/EBITDA": b["ev_ebitda_sector"],
                                          "latest operating profit ₹ Cr": round(latest_op), "average operating profit ₹ Cr": round(avg), "years": len(ops)},
            "explain": f"Today's enterprise value against average operating profit of the last {len(ops)} years: {mid:.1f}× (vs {ev_e:.1f}× on the latest year). "
                       + ("Current profit is above its average, so the latest multiple flatters the stock." if latest_op > 1.1 * avg else
                          "Current profit is below its average, so the latest multiple makes the stock look dearer than over a full cycle." if latest_op < 0.9 * avg else
                          "Current profit is close to its average."),
            "reading": f"{mid:.1f}× cycle-average profit"}


def m_pb_history(b, price, hist=None, **_):
    pbs = [h["pb"] for h in (hist or []) if h.get("pb")]
    pb = b["pb"]
    if not pb:
        return {"available": False, "reason": "Needs P/B."}
    figs = {"P/B now": pb, "sector P/B": b["pb_sector"]}
    txt = f"P/B {pb:.2f}"
    reading = None
    if pbs:
        avg = sum(pbs) / len(pbs)
        figs.update({"own average P/B": round(avg, 2), "own low": min(pbs), "own high": max(pbs), "years": len(pbs)})
        txt += f" against its own average of {avg:.2f} (range {min(pbs):.2f}–{max(pbs):.2f}, {len(pbs)} year-ends)."
        reading = "below own average" if pb < 0.85 * avg else "above own average" if pb > 1.15 * avg else "near own average"
    if b["roe"] is not None:
        txt += f" Return on equity {b['roe']:.1f}%."
    return {"available": True, "figures": figs, "explain": txt + " In a cyclical industry, buying near book value at the bottom of the cycle has historically been safer than buying low P/E at the top.",
            "reading": reading}


def m_p_sales(b, price, **_):
    rev, shares = b["latest"].get("revenue"), b["shares"]
    if not (rev and shares and price):
        return {"available": False, "reason": "Needs revenue and share count."}
    ps = price * shares / rev
    return {"available": True, "figures": {"price/sales": round(ps, 2)}, "explain": f"Market value is {ps:.2f}× annual revenue.", "reading": f"{ps:.2f}× sales"}


def _needs(what: str, how: str):
    def f(b, price, **_):
        return {"available": False, "needs_document": True, "reason": f"Needs {what}, which is not in the data feed. {how}"}
    return f


METHODS = {
    "pb_roe": m_pb_roe, "residual_income": m_residual_income, "dcf_earnings": m_dcf_earnings, "reverse_dcf": m_reverse_dcf,
    "pe_growth": m_pe_growth, "normalised_pe": m_normalised_pe, "mid_cycle_ev_ebitda": m_mid_cycle_ev_ebitda,
    "pb_history": m_pb_history, "p_sales": m_p_sales,
    "ev_replacement": _needs("installed capacity (million tonnes)", "The live analysis reads capacity from the latest annual report or investor presentation, works out EV per tonne, and compares it with the cost per tonne of new plants the industry reports."),
    "p_ev": _needs("embedded value", "The live analysis reads embedded value and VNB margin from the investor presentation."),
    "p_nav": _needs("net asset value of land and projects", "The live analysis uses the company's or analysts' published NAV, or pre-sales and land bank from the investor presentation."),
    "sotp": _needs("each business's profit", "The live analysis values each segment from the segment results in the annual report on its own industry's method and adds them up."),
}


# ------------------------------------------------------------------ cycle

def _range_position(xs: list[float], x: float) -> float | None:
    lo, hi = min(xs), max(xs)
    return None if hi == lo else (x - lo) / (hi - lo)


def commodity_position(series_id: str) -> dict | None:
    pts = macro._points(series_id)
    if len(pts) < 12:
        return None
    cfg = macro.load_series().get(series_id, {})
    if cfg.get("transform") == "yoy":
        pts = macro.yoy(pts)
    vals = [v for _, v in pts[-60:] if v is not None] if cfg.get("kind") == "reading" else [v for _, v in pts if v is not None]
    if len(vals) < 12:
        return None
    last_d, last = pts[-1]
    pos = _range_position(vals, last)
    year_ago = macro._value_near(pts, __import__("datetime").date.fromisoformat(last_d[:10]).replace(year=int(last_d[:4]) - 1))
    chg = round((last / year_ago[1] - 1) * 100, 1) if year_ago and year_ago[1] and cfg.get("kind") == "level" else None
    return {"series": series_id, "label": cfg.get("label", series_id), "latest": round(last, 2), "unit": cfg.get("unit", ""), "as_of": last_d[:10],
            "position_pct": None if pos is None else round(pos * 100), "low": round(min(vals), 2), "high": round(max(vals), 2),
            "change_12m_pct": chg, "source": f"{cfg.get('source', '').upper()} {cfg.get('ref', '')}".strip()}


def cycle_position(industry: str, fin: dict, quarterly: dict | None = None, b: dict | None = None,
                   products: list[str] | None = None, commodity: str | None = None) -> dict:
    """Where a commodity business stands in its cycle: the price of what it sells against its own range (the
    commodity cycle itself), its margin and earnings against their range, and Lynch's low-P/E-at-the-peak test.
    `products`: price series of what the company sells (e.g. zinc for a zinc miner). Without `commodity`,
    falls back to the industry setting."""
    g = guide(industry)
    if commodity is None and not g["cyclical"]:
        return {"cyclical": False, "note": f"{g['kind']}: not treated as a cyclical business."}
    rows = [r for r in (fin.get("periods") or []) if r.get("operating_margin_pct") is not None]
    ev, score, n = [], 0, 0
    if len(rows) >= 3:
        m = [r["operating_margin_pct"] for r in rows]
        pos = _range_position(m, m[0])
        trend = "rising" if m[0] > m[1] else "falling"
        ev.append(f"Operating margin {m[0]:.1f}% in {rows[0]['period']}: {'unchanged across' if pos is None else 'the highest' if pos == 1 else 'the lowest' if pos == 0 else f'{pos * 100:.0f}% of the way from lowest'} "
                  f"of the last {len(m)} years ({min(m):.1f}%–{max(m):.1f}%), {trend} from {m[1]:.1f}%.")
        if pos is not None:
            score += pos * 2 - 1
            n += 1
    q = quarterly or {}
    qr, qo = q.get("revenue") or [], q.get("operating_profit") or []
    if len(qr) >= 4 and len(qo) >= 4 and all(x.get("value") for x in qr[:4]):
        qm = [o["value"] / r["value"] * 100 for o, r in zip(qo[:4], qr[:4])]
        ev.append(f"Last 4 quarters' operating margin (newest first): {', '.join(f'{x:.1f}%' for x in qm)}"
                  + (" — improving." if qm[0] > qm[-1] + 1 else " — weakening." if qm[0] < qm[-1] - 1 else " — flat."))
    eps_rows = [r["eps"] for r in fin.get("periods") or [] if r.get("eps") is not None]
    if len(eps_rows) >= 3:
        avg = sum(eps_rows) / len(eps_rows)
        if avg > 0:
            ratio = eps_rows[0] / avg
            ev.append(f"Latest EPS is {ratio:.2f}× its {len(eps_rows)}-year average.")
            score += max(-1, min(1, (ratio - 1) * 2.5))
            n += 1
    sold = [c for c in (commodity_position(x) for x in (products or [])) if c]
    for c in sold:  # the price of what the company sells is the cycle itself: counts double
        if c["position_pct"] is not None:
            score += 2 * (c["position_pct"] / 100 * 2 - 1)
            n += 2
    comm = sold + [c for c in (commodity_position(x) for x in g["cycle_signals"] if x not in (products or [])) if c]
    for c in comm:
        if c["position_pct"] is not None:
            ev.append(f"{c['label']}: {c['latest']:,} {c['unit']} ({c['as_of']}), {c['position_pct']}% of the way up its range of {c['low']:,}–{c['high']:,}"
                      + (f", {c['change_12m_pct']:+.1f}% in 12 months" if c["change_12m_pct"] is not None else "") + ".")
    stage = "not enough history"
    if n:
        s = score / n
        rising = len(rows) >= 2 and rows[0]["operating_margin_pct"] > rows[1]["operating_margin_pct"]
        stage = ("near the top of its cycle" if s > 0.5 else "near the bottom of its cycle" if s < -0.5 else
                 "in an upswing" if rising else "in a downswing")
    lynch = None
    if b and b.get("pe") and stage == "near the top of its cycle" and b["pe_sector"] and b["pe"] < b["pe_sector"]:
        lynch = "Low P/E while profits are near their peak: Lynch warns this is often when cyclicals are most expensive."
    elif b and b.get("pe") and stage == "near the bottom of its cycle" and b["pe_sector"] and b["pe"] > b["pe_sector"]:
        lynch = "High P/E while profits are depressed: for cyclicals this is often near the bottom, when earnings later recover."
    return {"cyclical": True, "stage": stage, "evidence": ev, "commodities": comm, "lynch": lynch, "commodity": commodity,
            "how": (f"A {commodity} business: the stage weighs the price of what it sells against its range (double weight) with its own margin and earnings against theirs." if commodity
                    else "The stage comes from the company's own margins and earnings against their range."),
            "note": f"Only {len(rows)} years of company data are available from Upstox, so 'top' and 'bottom' are within that window; a full cycle is often 5–10 years."}


# ------------------------------------------------------------------ all together

def assess(industry: str, fin: dict, kr: dict, price: float | None, candles: list[dict] | None = None,
           quarterly: dict | None = None) -> dict:
    """The industry's method guide, the cycle (if cyclical), and every primary and secondary method worked out."""
    g = guide(industry)
    b = _basics(fin, kr, price)
    hist = analysis.history_multiples(fin, candles or []) if candles and fin.get("periods") else []
    cyc = cycle_position(industry, fin, quarterly, b)
    ids = [m["id"] for m in g["primary"]] + [m["id"] for m in g["secondary"]]
    if b["pat"] is not None and b["pat"] <= 0 and "p_sales" not in ids:
        ids.append("p_sales")  # loss-making: earnings methods fail, so add price-to-sales
    results = []
    for mid in ids:
        try:
            r = METHODS[mid](b, price, hist=hist)
        except (ZeroDivisionError, TypeError, ValueError) as e:
            r = {"available": False, "reason": f"Could not compute ({e})."}
        r.update({"id": mid, "name": NAMES[mid], "role": "primary" if mid in [m["id"] for m in g["primary"]] else "secondary"})
        results.append(r)
    values = [r["value"] for r in results if r.get("available") and r.get("value") and r["role"] == "primary" and r["id"] != "normalised_pe"]
    summary = None
    if values and price:
        lo, hi = min(values), max(values)
        summary = (f"Primary methods put value at ₹{lo:,.2f}" + (f"–₹{hi:,.2f}" if hi != lo else "") + f" against a price of ₹{price:,.2f}. "
                   + ("The price is below that range." if price < lo * 0.95 else "The price is above that range." if price > hi * 1.05 else "The price is inside that range."))
    return {"guide": g, "cycle": cyc, "methods": results, "summary": summary,
            "label": "Valuation by the methods that suit this industry. A screening output, not advice."}
