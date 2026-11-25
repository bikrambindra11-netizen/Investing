"""Everything that can be calculated from a company's own statements (P&L, balance sheet, cash flow),
year by year, plus the standard statement-based tests (DuPont, Piotroski F-score, Altman Z'', Sloan
accruals) and the market multiples on those figures.

Inputs are Upstox fundamentals (₹ crore, consolidated where filed, else standalone). Upstox publishes the
main lines only: no borrowings, inventory, receivables, fixed assets, interest or depreciation. Tests that
need those lines use the nearest available line and say so in `note`, or are skipped."""
from . import analysis

FIN = {"banks", "nbfc", "insurance"}


def _t(f, name, key="particular"):
    return analysis._table(((f.get(name) or {}).get("data") or {}).get("full_statement"), key)


def _r(x, nd=2):
    return None if x is None else round(x, nd)


def _div(a, b, pct=False):
    if a is None or b in (None, 0):
        return None
    return a / b * (100 if pct else 1)


def _avg(a, b):
    return a if b is None else (b if a is None else (a + b) / 2)


def years(f: dict) -> list[dict]:
    """Every statement line and every ratio for each year, newest first."""
    it, bt, ct = _t(f, "income"), _t(f, "balance"), _t(f, "cashflow")
    cats = analysis._table(((f.get("income") or {}).get("data") or {}).get("income_statement"), "category")
    g = lambda tbl, *names: next((tbl[n] for n in names if n in tbl), {})  # noqa: E731
    rev, oth, tot, exp = g(it, "Revenue"), g(it, "Other Income"), g(it, "Total Revenue"), g(it, "Total Expenses")
    rev = {**(cats.get("revenue") or {}), **rev} if not rev else rev
    pbt, tax, pat = g(it, "Profit Before Tax"), g(it, "Tax"), g(it, "Profit After Tax")
    eps_raw = g(it, "EPS - Basic")
    eps = analysis.adjust_eps(eps_raw, pat)["values"]
    dil = g(it, "EPS - Diluted")
    nca, ca, ta = g(bt, "Non-Current Assets"), g(bt, "Current Assets"), g(bt, "Total Assets")
    cl, ncl, eq = g(bt, "Current Liabilities"), g(bt, "Non-Current Liabilities"), g(bt, "Equity Capital")
    cfo, cfi, cff = g(ct, "Cash flow from Operations"), g(ct, "Cash flow from Investing"), g(ct, "Cash flow from Financing")
    pre_wc, dwc = g(ct, "Income before WC changes"), g(ct, "Change in WC")
    cash_end, cash_start = g(ct, "Cash (End of the year)"), g(ct, "Cash (Start of the year)")
    periods = sorted(set(rev) | set(pat) | set(ta), key=lambda p: analysis.period_end(p) or 0, reverse=True)
    out = []
    for i, p in enumerate(periods):
        q = periods[i + 1] if i + 1 < len(periods) else None
        R, PAT, PBT = rev.get(p), pat.get(p), pbt.get(p)
        TA, EQ, CL, NCL, CA, NCA = ta.get(p), eq.get(p), cl.get(p), ncl.get(p), ca.get(p), nca.get(p)
        CFO, CFI, CFF = cfo.get(p), cfi.get(p), cff.get(p)
        shares = _div(PAT, eps.get(p)) if PAT and eps.get(p) else None
        cap_emp = (TA - CL) if TA is not None and CL is not None else None
        avg_ta = _avg(TA, ta.get(q)) if q else TA
        avg_eq = _avg(EQ, eq.get(q)) if q else EQ
        fcf = CFO + CFI if CFO is not None and CFI is not None else None
        y = {
            "period": p,
            # P&L
            "revenue": R, "other_income": oth.get(p), "total_revenue": tot.get(p), "expenses": exp.get(p),
            "pbt": PBT, "tax": tax.get(p), "pat": PAT, "eps": _r(eps.get(p)), "eps_diluted": dil.get(p),
            "pbt_margin_pct": _r(_div(PBT, R, True), 1), "net_margin_pct": _r(_div(PAT, tot.get(p) or R, True), 1),
            "expense_ratio_pct": _r(_div(exp.get(p), tot.get(p), True), 1),
            "tax_rate_pct": _r(_div(tax.get(p), PBT, True), 1) if PBT and PBT > 0 else None,
            "other_income_share_pct": _r(_div(oth.get(p), PBT, True), 1) if PBT and PBT > 0 else None,
            # Balance sheet
            "total_assets": TA, "non_current_assets": NCA, "current_assets": CA,
            "current_liabilities": CL, "non_current_liabilities": NCL, "equity": EQ,
            "working_capital": (CA - CL) if CA is not None and CL is not None else None,
            "capital_employed": cap_emp, "shares_cr": _r(shares, 3),
            "book_value_per_share": _r(_div(EQ, shares)),
            "current_ratio": _r(_div(CA, CL)), "liabilities_to_equity": _r(_div((CL or 0) + (NCL or 0), EQ)) if CL is not None else None,
            "long_term_liabilities_to_assets": _r(_div(NCL, TA)), "equity_to_assets": _r(_div(EQ, TA)),
            "working_capital_to_assets": _r(_div((CA - CL) if CA is not None and CL is not None else None, TA)),
            # Returns (on average balances when the previous year exists)
            "roe_pct": _r(_div(PAT, avg_eq, True), 1), "roa_pct": _r(_div(PAT, avg_ta, True), 1),
            "pretax_roce_pct": _r(_div(PBT, cap_emp, True), 1),
            "asset_turnover": _r(_div(R, avg_ta)), "non_current_asset_turnover": _r(_div(R, NCA)),
            "equity_multiplier": _r(_div(avg_ta, avg_eq)),
            # Cash flow
            "cfo": CFO, "cfi": CFI, "cff": CFF, "free_cash_flow": fcf, "income_before_wc": pre_wc.get(p), "change_in_wc": dwc.get(p),
            "cash_end": cash_end.get(p), "cash_start": cash_start.get(p),
            "cfo_to_pat": _r(_div(CFO, PAT)) if PAT and PAT > 0 else None,
            "fcf_to_pat": _r(_div(fcf, PAT)) if PAT and PAT > 0 else None,
            "fcf_margin_pct": _r(_div(fcf, R, True), 1),
            "reinvestment_rate_pct": _r(_div(-CFI, CFO, True), 0) if CFO and CFO > 0 and CFI is not None else None,
            "accruals_to_assets_pct": _r(_div((PAT - CFO) if PAT is not None and CFO is not None else None, avg_ta, True), 1),
            "cash_to_assets_pct": _r(_div(cash_end.get(p), TA, True), 1),
        }
        if q:
            for k, prev in (("revenue_growth_pct", rev.get(q)), ("pat_growth_pct", pat.get(q)), ("eps_growth_pct", eps.get(q)),
                            ("book_value_growth_pct", eq.get(q)), ("assets_growth_pct", ta.get(q))):
                cur = {"revenue_growth_pct": R, "pat_growth_pct": PAT, "eps_growth_pct": eps.get(p),
                       "book_value_growth_pct": EQ, "assets_growth_pct": TA}[k]
                y[k] = _r((cur / prev - 1) * 100, 1) if cur is not None and prev and prev > 0 else None
        out.append(y)
    # Shares issued: change in share count (PAT / EPS) year on year
    for a, b in zip(out, out[1:]):
        if a["shares_cr"] and b["shares_cr"]:
            a["share_count_change_pct"] = _r((a["shares_cr"] / b["shares_cr"] - 1) * 100, 1)
    return out


def dupont(y: dict) -> dict | None:
    nm, at, em = y.get("net_margin_pct"), y.get("asset_turnover"), y.get("equity_multiplier")
    if None in (nm, at, em):
        return None
    return {"net_margin_pct": nm, "asset_turnover": at, "equity_multiplier": em, "roe_pct": _r(nm * at * em, 1),
            "reading": ("margins" if nm >= 15 else "asset use" if at >= 1.5 else "leverage" if em >= 3 else "a mix of margin and asset use")
            + " drive most of the return on equity"}


def piotroski(ys: list[dict], financial: bool) -> dict:
    """Piotroski (2000) F-score, nine tests on this year vs last. Substitutes, where Upstox lacks a line,
    are stated: long-term liabilities for long-term debt, pre-tax margin for gross margin."""
    if len(ys) < 2:
        return {"available": False, "reason": "Needs two years of statements."}
    a, b = ys[0], ys[1]
    tests = []

    def t(name, ok, value, note=None):
        tests.append({"test": name, "pass": None if ok is None else bool(ok), "value": value, "note": note})

    t("Profitable (ROA > 0)", None if a["roa_pct"] is None else a["roa_pct"] > 0, a["roa_pct"])
    t("Positive operating cash flow", None if a["cfo"] is None else a["cfo"] > 0, a["cfo"])
    t("ROA improved", None if None in (a["roa_pct"], b["roa_pct"]) else a["roa_pct"] > b["roa_pct"], f"{b['roa_pct']} → {a['roa_pct']}")
    t("Cash flow above profit (quality of earnings)", None if None in (a["cfo"], a["pat"]) else a["cfo"] > a["pat"], f"CFO {a['cfo']} vs PAT {a['pat']}")
    if financial:
        t("Long-term leverage fell", None, None, "skipped for lenders and insurers")
        t("Current ratio improved", None, None, "skipped for lenders and insurers")
    else:
        la, lb = a["long_term_liabilities_to_assets"], b["long_term_liabilities_to_assets"]
        t("Long-term leverage fell", None if None in (la, lb) else la <= lb, f"{lb} → {la}", "long-term liabilities ÷ assets (borrowings not reported separately)")
        t("Current ratio improved", None if None in (a["current_ratio"], b["current_ratio"]) else a["current_ratio"] > b["current_ratio"], f"{b['current_ratio']} → {a['current_ratio']}")
    sc = a.get("share_count_change_pct")
    t("No new shares issued", None if sc is None else sc <= 1, sc, "share count from profit ÷ EPS")
    t("Margin improved", None if None in (a["pbt_margin_pct"], b["pbt_margin_pct"]) else a["pbt_margin_pct"] > b["pbt_margin_pct"],
      f"{b['pbt_margin_pct']}% → {a['pbt_margin_pct']}%", "pre-tax margin (gross margin not reported)")
    t("Asset turnover improved", None if None in (a["asset_turnover"], b["asset_turnover"]) else a["asset_turnover"] > b["asset_turnover"], f"{b['asset_turnover']} → {a['asset_turnover']}")
    judged = [x for x in tests if x["pass"] is not None]
    score = sum(x["pass"] for x in judged)
    return {"available": True, "score": score, "of": len(judged), "period": a["period"], "tests": tests,
            "reading": "strong (8-9 of 9 in Piotroski's study)" if len(judged) == 9 and score >= 8 else
                       "weak (0-2)" if score <= 2 else "middling"}


def altman(y: dict, market_cap: float | None, financial: bool) -> dict:
    """Altman Z'' for emerging-market and non-manufacturing firms (Altman 2005):
    6.56·WC/TA + 3.26·RE/TA + 6.72·EBIT/TA + 1.05·equity/liabilities. Upstox has no retained earnings or
    EBIT, so book equity stands in for retained earnings (overstates) and pre-tax profit for EBIT
    (understates); treat as approximate."""
    if financial:
        return {"available": False, "reason": "Not meaningful for lenders and insurers."}
    ta, wc, eq, pbt = y.get("total_assets"), y.get("working_capital"), y.get("equity"), y.get("pbt")
    liab = (y.get("current_liabilities") or 0) + (y.get("non_current_liabilities") or 0)
    if not ta or None in (wc, eq, pbt) or not liab:
        return {"available": False, "reason": "Missing balance-sheet lines."}
    z = 6.56 * wc / ta + 3.26 * eq / ta + 6.72 * pbt / ta + 1.05 * eq / liab
    return {"available": True, "z": _r(z), "period": y["period"],
            "zone": "safe (above 2.6)" if z > 2.6 else "grey (1.1-2.6)" if z >= 1.1 else "distress (below 1.1)",
            "note": "Approximate: book equity used for retained earnings and pre-tax profit for EBIT."}


def multiples(y: dict, price: float | None, kr: dict) -> dict:
    sh = y.get("shares_cr")
    mcap = price * sh if price and sh else None
    out = {"market_cap_cr": _r(mcap, 0), "price": price}
    if mcap:
        out.update({"pe": _r(_div(mcap, y["pat"])) if y.get("pat") and y["pat"] > 0 else None,
                    "pb": _r(_div(mcap, y["equity"])) if y.get("equity") and y["equity"] > 0 else None,
                    "ps": _r(_div(mcap, y["revenue"])), "p_cfo": _r(_div(mcap, y["cfo"])) if y.get("cfo") and y["cfo"] > 0 else None,
                    "earnings_yield_pct": _r(_div(y["pat"], mcap, True), 1), "fcf_yield_pct": _r(_div(y["free_cash_flow"], mcap, True), 1),
                    "cash_to_market_cap_pct": _r(_div(y.get("cash_end"), mcap, True), 1)})
    out["ev_ebitda_upstox"] = (kr.get("EV/EBITDA") or {}).get("company")
    out["roce_upstox"] = (kr.get("ROCE") or {}).get("company")
    return out


def checks(ys: list[dict], financial: bool) -> list[dict]:
    """Plain-English red and green flags from the statements."""
    out = []
    if not ys:
        return out
    a = ys[0]
    cf = [y["cfo_to_pat"] for y in ys if y.get("cfo_to_pat") is not None]
    if cf and not financial:
        tot_cfo = sum(y["cfo"] for y in ys if y.get("cfo") is not None and y.get("pat"))
        tot_pat = sum(y["pat"] for y in ys if y.get("cfo") is not None and y.get("pat"))
        r = tot_cfo / tot_pat if tot_pat > 0 else None
        if r is not None:
            out.append({"flag": "good" if r >= 0.9 else "bad" if r < 0.6 else "watch",
                        "text": f"Over {len(cf)} years operating cash flow was {r:.2f}× reported profit" + (" — profits are backed by cash." if r >= 0.9 else " — a large part of profit has not turned into cash." if r < 0.6 else ".")})
    fcfs = [y["free_cash_flow"] for y in ys if y.get("free_cash_flow") is not None]
    if fcfs and not financial:
        neg = sum(x < 0 for x in fcfs)
        out.append({"flag": "bad" if neg == len(fcfs) else "good" if neg == 0 else "watch",
                    "text": f"Free cash flow (operating + investing) was negative in {neg} of {len(fcfs)} years; total ₹{sum(fcfs):,.0f} Cr."})
    if a.get("other_income_share_pct") is not None and a["other_income_share_pct"] > 30:
        out.append({"flag": "watch", "text": f"Other income is {a['other_income_share_pct']}% of pre-tax profit in {a['period']}: a big part of profit is not from the main business."})
    if a.get("tax_rate_pct") is not None and a["tax_rate_pct"] < 15:
        out.append({"flag": "watch", "text": f"Effective tax rate {a['tax_rate_pct']}% in {a['period']}: unusually low; check for one-offs or tax breaks."})
    if a.get("share_count_change_pct") and a["share_count_change_pct"] > 3:
        out.append({"flag": "watch", "text": f"Share count rose {a['share_count_change_pct']}% in {a['period']}: shareholders were diluted."})
    if not financial and a.get("current_ratio") is not None:
        out.append({"flag": "good" if a["current_ratio"] >= 1.5 else "bad" if a["current_ratio"] < 1 else "watch",
                    "text": f"Current ratio {a['current_ratio']} in {a['period']}" + (": short-term liabilities exceed short-term assets." if a["current_ratio"] < 1 else ".")})
    if a.get("accruals_to_assets_pct") is not None and not financial and a["accruals_to_assets_pct"] > 7:
        out.append({"flag": "bad", "text": f"Accruals {a['accruals_to_assets_pct']}% of assets in {a['period']}: profit well above cash flow (Sloan found high-accrual firms tend to see earnings fall back)."})
    cffs = [y["cff"] for y in ys if y.get("cff") is not None]
    if cffs:
        out.append({"flag": "neutral", "text": f"Financing cash flow over {len(cffs)} years: ₹{sum(cffs):,.0f} Cr "
                    + ("(net cash raised from lenders or shareholders)." if sum(cffs) > 0 else "(net cash paid out as repayments, dividends or buybacks).")})
    pats = [y["pat"] for y in ys if y.get("pat") is not None]
    if pats:
        out.append({"flag": "good" if all(p > 0 for p in pats) else "bad", "text": f"Profitable in {sum(p > 0 for p in pats)} of {len(pats)} years."})
    return out


def analyse(industry: str, f: dict, price: float | None) -> dict:
    """The full statement analysis for one company."""
    financial = industry in FIN
    ys = years(f)
    if not ys:
        return {"available": False, "reason": "No statements published by the data source."}
    kr = analysis.key_ratios(f)
    n = len(ys)
    span = n - 1

    def cagr(k):
        a, b = ys[0].get(k), ys[-1].get(k)
        return _r(analysis.cagr(a, b, span), 1) if span >= 1 else None

    return {"available": True, "years": ys, "dupont": dupont(ys[0]), "piotroski": piotroski(ys, financial),
            "altman": altman(ys[0], multiples(ys[0], price, kr)["market_cap_cr"], financial),
            "multiples": multiples(ys[0], price, kr), "checks": checks(ys, financial),
            "cagr": {"revenue_pct": cagr("revenue"), "pat_pct": cagr("pat"), "eps_pct": cagr("eps"), "book_value_pct": cagr("equity"),
                     "cfo_pct": cagr("cfo"), "years": span},
            "basis": ((f.get("income") or {}).get("data") or {}).get("type"),
            "not_in_feed": "Borrowings, inventory, receivables, fixed assets, interest and depreciation are not in the data feed, so debt/equity, interest cover, working-capital days and EBITDA from statements are not calculated.",
            "source": "Upstox fundamentals: income statement, balance sheet, cash flow (₹ crore)"}
