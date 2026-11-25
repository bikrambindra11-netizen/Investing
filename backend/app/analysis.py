"""Company (micro) analysis: financial history, ratios, Graham checks, valuation, risks, and the
final screening summary. Every number carries its source and period. Missing data is reported as
"not available", never estimated."""
from datetime import date

FINANCIAL_INDUSTRIES = {"banks", "nbfc", "insurance"}
CAPITAL_HEAVY = {"metals", "power", "oil_gas", "cement", "capital_goods", "realty"}
GRAHAM_MIN_REVENUE_CR = 1000  # "adequate size": annual revenue of at least ₹1,000 crore

MONTHS = {m: i for i, m in enumerate(["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                                      "Sep", "Oct", "Nov", "Dec"]) if m}


def period_end(label: str) -> date | None:
    """'Mar 2025' -> 2025-03-31."""
    try:
        mon, yr = label.split()
        m, y = MONTHS[mon[:3]], int(yr)
    except (ValueError, KeyError):
        return None
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def _table(rows: list[dict] | None, key: str = "particular") -> dict[str, dict[str, float]]:
    """[{particular, history:[{period, value}]}] -> {particular: {period: value}}."""
    out: dict[str, dict[str, float]] = {}
    for r in rows or []:
        out[r[key]] = {h["period"]: h["value"] for h in r.get("history", []) if h.get("value") is not None}
    return out


def _years(*series: dict[str, float]) -> list[str]:
    """Periods present in all given series, newest first."""
    common = set.intersection(*(set(s) for s in series if s)) if any(series) else set()
    return sorted(common, key=lambda p: period_end(p) or date.min, reverse=True)


def cagr(new: float | None, old: float | None, years: int) -> float | None:
    if new is None or old is None or years <= 0 or old <= 0 or new <= 0:
        return None
    return round(((new / old) ** (1 / years) - 1) * 100, 1)


def _ratio(a: float | None, b: float | None, pct: bool = False) -> float | None:
    if a is None or not b:
        return None
    return round(a / b * (100 if pct else 1), 2 if not pct else 1)


def _num(v) -> float | None:
    """'20.15' / '8.94%' / 20.15 -> float."""
    if v is None:
        return None
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def close_on_or_before(candles: list[dict], d: date) -> float | None:
    iso = d.isoformat()
    best = None
    for c in candles:
        if c["date"] <= iso:
            best = c["close"]
        else:
            break
    return best


# ------------------------------------------------------------------ price stats

def price_stats(candles: list[dict]) -> dict:
    if not candles:
        return {"available": False}
    last = candles[-1]
    d_last = date.fromisoformat(last["date"])

    def back(days: int) -> float | None:
        return close_on_or_before(candles, date.fromordinal(d_last.toordinal() - days))

    year = [c for c in candles if c["date"] >= date.fromordinal(d_last.toordinal() - 365).isoformat()]
    q = [c for c in candles if c["date"] >= date.fromordinal(d_last.toordinal() - 91).isoformat()]
    hi = max(c["high"] for c in year)
    lo = min(c["low"] for c in year)

    def ret(days: int, years: float | None = None) -> float | None:
        p = back(days)
        if p is None or candles[0]["date"] > date.fromordinal(d_last.toordinal() - days).isoformat():
            return None
        if years:
            return cagr(last["close"], p, years)
        return round((last["close"] / p - 1) * 100, 1)

    return {
        "available": True,
        "as_of": last["date"],
        "close": last["close"],
        "high_52w": hi,
        "low_52w": lo,
        "from_high_pct": round((last["close"] / hi - 1) * 100, 1),
        "return_1m": ret(30), "return_6m": ret(182), "return_1y": ret(365),
        "cagr_3y": ret(365 * 3, 3), "cagr_5y": ret(365 * 5, 5),
        "avg_volume_3m": round(sum(c["volume"] for c in q) / len(q)) if q else None,
    }


# ------------------------------------------------------------------ financials

def adjust_eps(eps: dict[str, float], pat: dict[str, float]) -> dict:
    """Restate older EPS for bonus issues and splits so years are comparable.

    Share count = profit / EPS. A jump of 40% or more in the share count between two years is
    treated as a bonus or split, and older EPS values are divided by that ratio."""
    periods = _years(eps, pat)
    values, adjustments = dict(eps), []
    factor = 1.0
    for newer, older in zip(periods, periods[1:]):
        if not (eps[newer] and eps[older] and pat[newer] and pat[older]) or eps[newer] <= 0 or eps[older] <= 0:
            continue
        ratio = (pat[newer] / eps[newer]) / (pat[older] / eps[older])
        if ratio >= 1.4:
            factor *= ratio
            adjustments.append({"between": f"{older} and {newer}", "ratio": round(ratio, 2)})
        values[older] = round(eps[older] / factor, 2)
    return {"values": values, "adjustments": adjustments}


def financials(f: dict) -> dict:
    """Year-by-year history built from Upstox statements (₹ crore)."""
    inc = (f.get("income") or {}).get("data") or {}
    bal = (f.get("balance") or {}).get("data") or {}
    cf = (f.get("cashflow") or {}).get("data") or {}
    it, bt, ct = _table(inc.get("full_statement")), _table(bal.get("full_statement")), _table(cf.get("full_statement"))
    cats = _table(inc.get("income_statement"), "category")

    cat_rev, cat_pat = cats.get("revenue") or {}, cats.get("net_profit") or {}
    revenue = {**cat_rev, **(it.get("Revenue") or {})}
    total_rev = {**cat_rev, **(it.get("Total Revenue") or {})}
    pat = {**cat_pat, **(it.get("Profit After Tax") or {})}
    pbt = it.get("Profit Before Tax") or {}
    eps = adjust_eps(it.get("EPS - Basic") or {}, pat)
    op = cats.get("operating_profit") or {}
    equity = bt.get("Equity Capital") or {}
    cfo = ct.get("Cash flow from Operations") or {}
    cfi = ct.get("Cash flow from Investing") or {}

    periods = _years(revenue, pat)
    rows = []
    for p in periods[:10]:
        rev = revenue.get(p)
        rows.append({
            "period": p,
            "revenue": rev,
            "operating_profit": op.get(p),
            "profit_before_tax": pbt.get(p),
            "net_profit": pat.get(p),
            "eps": eps["values"].get(p),
            "operating_margin_pct": _ratio(op.get(p), rev, pct=True),
            "net_margin_pct": _ratio(pat.get(p), total_rev.get(p) or rev, pct=True),
            "roe_pct": _ratio(pat.get(p), equity.get(p), pct=True),
            "cash_from_operations": cfo.get(p),
            "cfo_to_profit": _ratio(cfo.get(p), pat.get(p)),
            "investing_cash_flow": cfi.get(p),
            "total_assets": (bt.get("Total Assets") or {}).get(p),
            "equity": equity.get(p),
            "current_assets": (bt.get("Current Assets") or {}).get(p),
            "current_liabilities": (bt.get("Current Liabilities") or {}).get(p),
            "non_current_liabilities": (bt.get("Non-Current Liabilities") or {}).get(p),
            "net_current_assets": (bt.get("Net Current Asset") or {}).get(p),
        })
    for r in rows:
        liab = (r["current_liabilities"] or 0) + (r["non_current_liabilities"] or 0)
        r["liabilities_to_equity"] = _ratio(liab, r["equity"]) if r["current_liabilities"] is not None else None
        r["current_ratio"] = _ratio(r["current_assets"], r["current_liabilities"])

    n = len(rows)
    growth = {}
    for k, series in (("revenue", revenue), ("operating_profit", op), ("net_profit", pat)):
        ps = _years(series)
        span = min(len(ps) - 1, 5)
        if span >= 1:
            growth[f"{k}_cagr_pct"] = cagr(series[ps[0]], series[ps[span]], span)
            growth.setdefault("years", span)
    return {
        "periods": rows,
        "growth": growth,
        "eps_adjustments": eps["adjustments"],
        "years_available": n,
        "units": "₹ crore",
        "fetched_at": (f.get("income") or {}).get("fetched_at"),
    }


def shareholding(f: dict) -> dict:
    data = (f.get("holdings") or {}).get("data") or []
    t = _table(data, "category")
    names = {"promoters": "Promoters", "fii": "Foreign institutions (FII)", "mutual_funds": "Mutual funds",
             "other_dii": "Other domestic institutions", "retail_and_other": "Retail & others"}
    periods = _years(*[v for v in t.values() if v])[:8]
    rows = [{"category": names.get(k, k), "key": k, "values": [{"period": p, "pct": v.get(p)} for p in periods]}
            for k, v in t.items()]
    change = {}
    for r in rows:
        vals = [x["pct"] for x in r["values"] if x["pct"] is not None]
        if len(vals) >= 2:
            change[r["key"]] = round(vals[0] - vals[-1], 2)
    return {"periods": periods, "rows": rows, "change_over_period": change,
            "fetched_at": (f.get("holdings") or {}).get("fetched_at"),
            "pledge": "not available (not provided by the data source)"}


def capital_allocation(f: dict, fin: dict) -> dict:
    acts = (f.get("actions") or {}).get("data") or []
    events = []
    for a in acts:
        events.append({"type": a.get("name"), "date": a.get("expiry_date"), "amount": a.get("amount"),
                       "ratio": a.get("ratio"),
                       "details": next((d["value"] for d in a.get("event_details", []) if d["name"] == "Details"), None)})
    by_type: dict[str, int] = {}
    for e in events:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    capex = [{"period": r["period"], "investing_cash_flow": r["investing_cash_flow"]} for r in fin["periods"][:5]]
    return {"events": events[:20], "counts": by_type, "investing_cash_flow": capex,
            "note": "Investing cash flow (mostly capex and acquisitions; negative = money spent).",
            "fetched_at": (f.get("actions") or {}).get("fetched_at")}


# ------------------------------------------------------------------ valuation

def key_ratios(f: dict) -> dict[str, dict]:
    out = {}
    for r in (f.get("ratios") or {}).get("data") or []:
        out[r["name"]] = {"company": _num(r.get("company_value")), "sector": _num(r.get("sector_value"))}
    return out


def history_multiples(fin: dict, candles: list[dict]) -> list[dict]:
    """P/E and P/B at each financial year end, from the year-end share price."""
    out = []
    for r in fin["periods"]:
        d = period_end(r["period"])
        price = close_on_or_before(candles, d) if d else None
        pe = pb = None
        if price and r["eps"] and r["eps"] > 0:
            pe = round(price / r["eps"], 1)
            shares_cr = r["net_profit"] / r["eps"] if r["net_profit"] else None
            if shares_cr and r["equity"]:
                pb = round(price / (r["equity"] / shares_cr), 2)
        out.append({"period": r["period"], "price": price, "pe": pe, "pb": pb})
    return out


def valuation(industry: str, f: dict, fin: dict, candles: list[dict], price: float | None) -> dict:
    kr = key_ratios(f)
    hist = history_multiples(fin, candles)
    from .valuation_methods import guide  # the industry's methods (config/valuation_methods.yaml)
    g = guide(industry)
    to_ratio = {"pb_roe": "P/B", "residual_income": "P/B", "pb_history": "P/B", "p_ev": "P/B", "p_nav": "P/B",
                "mid_cycle_ev_ebitda": "EV/EBITDA", "ev_replacement": "EV/EBITDA", "sotp": "EV/EBITDA"}
    chosen = []
    for m in g["primary"] + g["secondary"]:
        r = to_ratio.get(m["id"], "P/E")
        if r not in chosen:
            chosen.append(r)
    for r in ("P/E", "EV/EBITDA", "P/B"):
        if len(chosen) < 2 and r not in chosen:
            chosen.append(r)
    chosen = chosen[:2]
    why = f"{g['kind']}: compared on {' and '.join(chosen)}. {g['why']}"

    metrics = []
    for m in chosen:
        cur = (kr.get(m) or {}).get("company")
        sector = (kr.get(m) or {}).get("sector")
        own = [h[m.lower().replace("/", "")] for h in hist[:5]] if m in ("P/E", "P/B") else []
        own = [x for x in own if x is not None]
        own_avg = round(sum(own) / len(own), 2) if own else None
        metrics.append({"name": m, "current": cur, "sector": sector, "own_avg": own_avg,
                        "own_years": len(own),
                        "vs_sector_pct": round((cur / sector - 1) * 100) if cur and sector else None,
                        "vs_own_pct": round((cur / own_avg - 1) * 100) if cur and own_avg else None})

    # Label from the main metric: cheaper than both its own history and its sector -> cheap.
    label = "not available"
    main = metrics[0]
    comps = [x for x in (main["vs_sector_pct"], main["vs_own_pct"]) if x is not None]
    if main["current"] is not None and main["current"] <= 0:
        label = "not meaningful (negative earnings)"
    elif comps:
        if all(x <= -15 for x in comps):
            label = "cheap"
        elif all(x >= 15 for x in comps):
            label = "expensive"
        else:
            label = "fair"
    return {"chosen": chosen, "why": why, "metrics": metrics, "label": label, "history": hist[:5],
            "all_ratios": kr, "price": price, "fetched_at": (f.get("ratios") or {}).get("fetched_at")}


# ------------------------------------------------------------------ Graham

def latest_with(rows: list[dict], *keys: str) -> dict:
    """Most recent year that has all the given figures ({} if none)."""
    return next((r for r in rows if all(r.get(k) is not None for k in keys)), {})


def graham(industry: str, fin: dict, f: dict, price: float | None) -> list[dict]:
    rows = fin["periods"]
    n = len(rows)
    latest = rows[0] if rows else {}
    checks = []

    def add(name, status, value, rule, note=None):
        checks.append({"name": name, "status": status, "value": value, "rule": rule, "note": note})

    # 1. Adequate size
    rev = latest.get("revenue")
    add("Adequate size", "not_available" if rev is None else ("pass" if rev >= GRAHAM_MIN_REVENUE_CR else "fail"),
        None if rev is None else f"Revenue ₹{rev:,.0f} Cr ({latest['period']})",
        f"Annual revenue of at least ₹{GRAHAM_MIN_REVENUE_CR:,} crore")

    # 2. Strong financial condition
    if industry in FINANCIAL_INDUSTRIES:
        add("Strong financial condition", "skipped", None, "Current ratio ≥ 2 and long-term debt ≤ net current assets",
            "Skipped for banks and lenders: their balance sheets are mostly loans and deposits, so the current ratio does not apply.")
    else:
        bs = latest_with(rows, "current_ratio")
        cr, nca, ncl = bs.get("current_ratio"), bs.get("net_current_assets"), bs.get("non_current_liabilities")
        if cr is None:
            add("Strong financial condition", "not_available", None, "Current ratio ≥ 2 and long-term debt ≤ net current assets")
        else:
            ok = cr >= 2 and (nca is not None and ncl is not None and ncl <= nca)
            add("Strong financial condition", "pass" if ok else "fail",
                f"Current ratio {cr}; long-term liabilities ₹{ncl:,.0f} Cr vs net current assets ₹{nca:,.0f} Cr ({bs['period']})"
                if nca is not None and ncl is not None else f"Current ratio {cr} ({bs['period']})",
                "Current ratio ≥ 2 and long-term debt ≤ net current assets",
                "Long-term debt is not reported separately, so all non-current liabilities are used (stricter).")

    # 3. Earnings stability
    profits = [r["net_profit"] for r in rows if r["net_profit"] is not None]
    if not profits:
        add("Earnings stability", "not_available", None, "Positive profit in each of the last 10 years")
    else:
        neg = sum(p <= 0 for p in profits)
        status = "fail" if neg else ("pass" if len(profits) >= 10 else "partial")
        add("Earnings stability", status, f"{len(profits) - neg} of {len(profits)} years profitable",
            "Positive profit in each of the last 10 years",
            None if len(profits) >= 10 else f"Only {len(profits)} years of data available.")

    # 4. Dividend record
    acts = (f.get("actions") or {}).get("data")
    if acts is None:
        add("Dividend record", "not_available", None, "Uninterrupted dividends (Graham: 20 years)")
    else:
        div_years = set()
        for a in acts:
            if (a.get("name") or "").lower().startswith("dividend") and a.get("expiry_date"):
                div_years.add(int(a["expiry_date"][-4:]))
        recent = max((int(r["period"][-4:]) for r in rows), default=date.today().year)
        if not div_years:
            add("Dividend record", "fail", "No dividends found", "Uninterrupted dividends (Graham: 20 years)",
                "Based on the corporate actions the data source lists.")
        else:
            paid_recently = any(y >= recent - 1 for y in div_years)
            add("Dividend record", "partial" if paid_recently else "fail",
                f"Dividends found in {len(div_years)} calendar year(s), latest {max(div_years)}",
                "Uninterrupted dividends (Graham: 20 years)",
                "The data source lists only recent corporate actions, so 20 years cannot be confirmed."
                if paid_recently else "No dividend in the last two years.")

    # 5. Earnings growth (3-year averages)
    eps = [r["eps"] for r in rows if r["eps"] is not None]
    if len(eps) < 6:
        add("Earnings growth", "not_available", f"{len(eps)} years of EPS", "EPS up ≥ 33% over 10 years (3-year averages)",
            "Needs at least 6 years of EPS.")
    else:
        new, old = sum(eps[:3]) / 3, sum(eps[-3:]) / 3
        g = round((new / old - 1) * 100, 1) if old > 0 else None
        status = "fail" if g is None or g < 33 else ("pass" if len(eps) >= 10 else "partial")
        add("Earnings growth", status, f"3-yr avg EPS ₹{old:.2f} → ₹{new:.2f} ({g:+.1f}%)" if g is not None else "not meaningful",
            "EPS up ≥ 33% over 10 years (3-year averages)", None if len(eps) >= 10 else f"Measured over {len(eps)} years.")

    # 6. Moderate P/E on 3-year average EPS
    if price is None or len(eps) < 3:
        add("Moderate P/E", "not_available", None, "Price ≤ 15 × average EPS of last 3 years")
    else:
        avg3 = sum(eps[:3]) / 3
        if avg3 <= 0:
            add("Moderate P/E", "fail", "Average EPS is negative", "Price ≤ 15 × average EPS of last 3 years")
        else:
            pe3 = round(price / avg3, 1)
            add("Moderate P/E", "pass" if pe3 <= 15 else "fail", f"P/E {pe3} on 3-yr avg EPS ₹{avg3:.2f}",
                "Price ≤ 15 × average EPS of last 3 years")

    # 7. Moderate price to book
    latest = latest_with(rows, "eps", "equity", "net_profit")
    if price is None or not latest:
        add("Moderate price to book", "not_available", None, "P/B ≤ 1.5, or P/E × P/B ≤ 22.5")
    else:
        shares_cr = latest["net_profit"] / latest["eps"]
        if latest["eps"] <= 0 or shares_cr <= 0:
            add("Moderate price to book", "fail", "Negative earnings", "P/B ≤ 1.5, or P/E × P/B ≤ 22.5")
        else:
            pb = round(price / (latest["equity"] / shares_cr), 2)
            pe = round(price / latest["eps"], 1)
            ok = pb <= 1.5 or pe * pb <= 22.5
            add("Moderate price to book", "pass" if ok else "fail",
                f"P/B {pb}, P/E {pe}, product {pe * pb:.1f} (book value and EPS of {latest['period']})",
                "P/B ≤ 1.5, or P/E × P/B ≤ 22.5")
    return checks


# ------------------------------------------------------------------ quality & risks

def quality(industry: str, fin: dict, kr: dict) -> dict:
    rows, g = fin["periods"], fin["growth"]
    items = []

    def add(name, ok, value):
        items.append({"name": name, "ok": ok, "value": value})

    rg = g.get("revenue_cagr_pct")
    if rg is not None:
        add("Revenue growth", rg >= 10, f"{rg}% a year over {g['years']} years")
    pg = g.get("net_profit_cagr_pct")
    if pg is not None:
        add("Profit growth", pg >= 10, f"{pg}% a year over {g['years']} years")
    m = [r["net_margin_pct"] for r in rows[:3] if r["net_margin_pct"] is not None]
    if len(m) >= 2:
        add("Margins holding up", m[0] >= m[-1] - 1, f"Net margin {m[-1]}% → {m[0]}%")
    roe = (kr.get("ROE") or {}).get("company") or latest_with(rows, "roe_pct").get("roe_pct")
    if roe is not None:
        add("Return on equity", roe >= 15, f"ROE {roe}%")
    roce = (kr.get("ROCE") or {}).get("company")
    if roce is not None and industry not in FINANCIAL_INDUSTRIES:
        add("Return on capital", roce >= 15, f"ROCE {roce}%")
    cfo = [r["cfo_to_profit"] for r in rows[:3] if r["cfo_to_profit"] is not None]
    if cfo:
        avg = round(sum(cfo) / len(cfo), 2)
        add("Profits turn into cash", avg >= 0.8, f"Operating cash flow = {avg}× profit (3-yr avg)")
    bs = latest_with(rows, "liabilities_to_equity")
    if bs and industry not in FINANCIAL_INDUSTRIES:
        le = bs["liabilities_to_equity"]
        add("Balance sheet not stretched", le <= 1.5, f"Total liabilities {le}× equity")
    return {"items": items, "passed": sum(i["ok"] for i in items), "total": len(items)}


def risks(industry: str, fin: dict, kr: dict, holdings: dict, stats: dict, macro: dict, val: dict) -> list[str]:
    out = []
    rows = fin["periods"]
    if rows and rows[0]["net_profit"] is not None and rows[0]["net_profit"] < 0:
        out.append("The company made a loss in its latest financial year.")
    if len(rows) >= 2 and rows[0]["net_profit"] and rows[1]["net_profit"] and rows[1]["net_profit"] > 0 \
            and rows[0]["net_profit"] < rows[1]["net_profit"] * 0.85:
        out.append(f"Profit fell {round((1 - rows[0]['net_profit'] / rows[1]['net_profit']) * 100)}% in the latest year.")
    cfo = [r["cfo_to_profit"] for r in rows[:3] if r["cfo_to_profit"] is not None]
    if cfo and sum(cfo) / len(cfo) < 0.5 and industry not in FINANCIAL_INDUSTRIES:
        out.append("Reported profits are not turning into cash (low operating cash flow).")
    bs = latest_with(rows, "liabilities_to_equity")
    if bs and bs["liabilities_to_equity"] > 2 and industry not in FINANCIAL_INDUSTRIES:
        out.append(f"High liabilities: {bs['liabilities_to_equity']}× equity ({bs['period']}).")
    prom = holdings.get("change_over_period", {}).get("promoters")
    if prom is not None and prom < -2:
        out.append(f"Promoters cut their stake by {abs(prom)} percentage points over the last {len(holdings['periods'])} quarters.")
    pe = kr.get("P/E") or {}
    if pe.get("company") and pe.get("sector") and pe["company"] > pe["sector"] * 1.5:
        out.append(f"Valued well above its sector (P/E {pe['company']} vs sector {pe['sector']}); high expectations are built in.")
    if val.get("label") == "expensive":
        out.append("Expensive versus both its own history and its sector.")
    if stats.get("available") and stats.get("from_high_pct") is not None and stats["from_high_pct"] <= -30:
        out.append(f"The share is {abs(stats['from_high_pct'])}% below its 52-week high; find out why before buying.")
    heads = [d for d in macro.get("drivers", []) if d["verdict"] == "headwind"]
    if heads:
        out.append("Economic headwinds for this industry: " + "; ".join(d["label"] for d in heads[:3]) + ".")
    if stats.get("available") and stats.get("avg_volume_3m") is not None and stats["avg_volume_3m"] < 10000:
        out.append("Thinly traded: it may be hard to buy or sell without moving the price.")
    return out


# ------------------------------------------------------------------ summary

def summary(name: str, macro: dict, qual: dict | None, graham_checks: list[dict] | None, val: dict | None,
            stats: dict) -> dict:
    reasons = []
    ms = macro["score"]
    macro_share = ms["share_tailwinds"]
    if macro_share is not None:
        reasons.append(f"Economy: {ms['tailwinds']} of {ms['judged']} drivers for {macro['label']} are tailwinds"
                       f" and {ms['headwinds']} are headwinds.")
    micro = None
    if qual and qual["total"]:
        g_pass = sum(c["status"] == "pass" for c in graham_checks or [])
        g_total = sum(c["status"] in ("pass", "fail", "partial") for c in graham_checks or [])
        micro = (qual["passed"] + g_pass) / (qual["total"] + g_total) if (qual["total"] + g_total) else None
        reasons.append(f"Business quality: passes {qual['passed']} of {qual['total']} quality checks.")
        if g_total:
            reasons.append(f"Graham's defensive-investor tests: {g_pass} of {g_total} passed.")
        best = [i for i in qual["items"] if i["ok"]][:1] + [i for i in qual["items"] if not i["ok"]][:1]
        for i in best:
            reasons.append(f"{i['name']}: {i['value']}.")
    vlabel = val["label"] if val else "not available"
    if val and val["metrics"] and val["metrics"][0]["current"] is not None:
        m = val["metrics"][0]
        bits = [f"{m['name']} {m['current']}"]
        if m["sector"] is not None:
            bits.append(f"sector {m['sector']}")
        if m["own_avg"] is not None:
            bits.append(f"own {m['own_years']}-yr average {m['own_avg']}")
        reasons.append(f"Valuation looks {vlabel}: " + ", ".join(bits) + ".")
    if stats.get("available") and stats.get("return_1y") is not None:
        reasons.append(f"Share price {stats['return_1y']:+.1f}% over 1 year.")

    if micro is None:
        verdict = (f"{name}: company financials are not loaded yet (they need the Upstox login), "
                   f"so only the economic backdrop can be judged — it is "
                   + ("supportive." if (macro_share or 0) >= 0.5 else "mixed." if (macro_share or 0) >= 0.25 else "unfavourable."))
        tone = "neutral"
    elif micro >= 0.6 and (macro_share or 0) >= 0.5 and vlabel in ("cheap", "fair"):
        verdict, tone = f"{name} looks attractive on this screen: a good business, a supportive economy and a reasonable price.", "positive"
    elif micro < 0.4 or (vlabel == "expensive" and (macro_share or 0) < 0.5):
        verdict, tone = f"{name} looks weak on this screen.", "negative"
    else:
        verdict, tone = f"{name} shows a mixed picture on this screen; look at the reasons below.", "neutral"
    return {"verdict": verdict, "tone": tone, "reasons": reasons[:6],
            "scores": {"macro_share_tailwinds": macro_share, "micro": round(micro, 2) if micro is not None else None,
                       "valuation": vlabel},
            "label": "Screening output only. Not investment advice."}


# ------------------------------------------------------------------ DCF and justified P/B

COST_OF_EQUITY = 12.5  # % a year: Indian risk-free ~7% plus an equity risk premium
TERMINAL_GROWTH = 5.0  # % a year after the forecast period (roughly long-run nominal GDP growth, conservatively)


def dcf(industry: str, fin: dict, kr: dict, price: float | None) -> dict:
    """Intrinsic value per share.

    Non-financial companies: earnings-based DCF. Profit grows at the recent rate (capped at 20% and at
    80% of ROE), fading to 5% over 10 years; the cash shareholders can take out each year is profit x
    (1 - growth / ROE), the part not needed to fund that growth; discounted at 12.5%. Lenders:
    justified P/B = (ROE - g) / (cost of equity - g) x book value per share."""
    rows = fin.get("periods") or []
    latest = latest_with(rows, "eps", "net_profit", "equity")
    if not latest or not latest.get("eps") or latest["eps"] <= 0:
        return {"available": False, "reason": "Needs positive earnings per share."}
    shares_cr = latest["net_profit"] / latest["eps"]
    g_hist = (fin.get("growth") or {}).get("net_profit_cagr_pct")
    g = max(0.0, min(20.0, g_hist if g_hist is not None else 8.0))
    ke, gt = COST_OF_EQUITY / 100, TERMINAL_GROWTH / 100
    if industry in FINANCIAL_INDUSTRIES:
        roe = (kr.get("ROE") or {}).get("company") or latest.get("roe_pct")
        if not roe:
            return {"available": False, "reason": "ROE not available."}
        bvps = latest["equity"] / shares_cr
        jpb = max(0.0, (roe / 100 - gt) / (ke - gt))
        value = bvps * jpb
        out = {"available": True, "method": "justified P/B", "value": round(value, 2),
               "assumptions": f"Book value ₹{bvps:,.2f}/share, ROE {roe:.1f}%, cost of equity {COST_OF_EQUITY}%, long-run growth {TERMINAL_GROWTH}% → justified P/B {jpb:.2f}."}
    else:
        roe = (kr.get("ROE") or {}).get("company") or latest.get("roe_pct")
        if not roe or roe <= 0:
            return {"available": False, "reason": "Needs a positive return on equity."}
        # Growth cannot exceed what the company's ROE can fund for long: cap it at 80% of ROE.
        g = max(0.0, min(g, 0.8 * roe))
        pat = latest["net_profit"]
        pv, earn = 0.0, pat
        steps = [g + (TERMINAL_GROWTH - g) * i / 9 for i in range(10)]  # 10 years, fading from g to the long-run rate
        for yr, gi in enumerate(steps, 1):
            earn *= 1 + gi / 100
            payout = max(0.0, 1 - gi / roe)  # what is left after reinvesting enough to grow at gi
            pv += earn * payout / (1 + ke) ** yr
        tv_payout = max(0.0, 1 - TERMINAL_GROWTH / roe)
        tv = earn * (1 + gt) * tv_payout / (ke - gt) / (1 + ke) ** 10
        value = (pv + tv) / shares_cr
        out = {"available": True, "method": "DCF (earnings)", "value": round(value, 2),
               "assumptions": f"Profit ₹{pat:,.0f} Cr ({latest['period']}), ROE {roe:.1f}%, growth {g:.1f}% a year fading to {TERMINAL_GROWTH}% over 10 years; "
                              f"each year's cash to shareholders = profit × (1 − growth ÷ ROE); discount rate {COST_OF_EQUITY}%; {shares_cr:,.1f} Cr shares."}
        fcfs = [(r["cash_from_operations"] or 0) + (r["investing_cash_flow"] or 0) for r in rows[:3]
                if r.get("cash_from_operations") is not None and r.get("investing_cash_flow") is not None]
        if fcfs:
            base = sum(fcfs) / len(fcfs)
            out["cash_flow_check"] = (f"Recent free cash flow (operating + investing, 3-yr avg) is ₹{base:,.0f} Cr a year"
                                      + (", well below profit: the company is investing heavily, so a DCF on today's cash flow would understate its value." if base < 0.5 * pat
                                         else ", in line with profit." if base < 1.3 * pat else ", above profit."))
    if price:
        out["upside_pct"] = round((out["value"] / price - 1) * 100, 1)
        out["margin_of_safety"] = "yes" if out["value"] >= price * 1.3 else "no"
    return out
