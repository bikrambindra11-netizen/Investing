"""Intrinsic value by Benjamin Graham's and Warren Buffett's methods, from the company's own statements.

Graham
  Graham number      = sqrt(22.5 x EPS x book value per share)   (P/E 15 x P/B 1.5, The Intelligent Investor ch. 14)
  Graham formula     = EPS x (8.5 + 2g) x 4.4 / Y                 (Graham's 1974 revision; g = expected growth % a year,
                                                                   Y = today's high-grade bond yield; 4.4 was the AAA yield in 1962)
  Defensive checks   size, current ratio >= 2, earnings every year, dividends, EPS growth, P/E <= 15, P/E x P/B <= 22.5
Buffett
  Owner earnings     cash the business generates after the investment it needs (here: operating cash flow + investing
                     cash flow, averaged; the feed has no maintenance-capex split, so this is conservative)
  Value              owner earnings grown for 10 years, then at the long-run rate, discounted at the long-term
                     government bond rate (Buffett's choice of discount rate), per share
  Quality checks     ROE >= 15% every year, earnings rising, positive owner earnings every year, modest liabilities,
                     good margins: Buffett only values businesses he can predict
For banks and other lenders, earnings replace owner earnings (their cash flows mix in deposits and loans)."""
from math import sqrt

# Which of the three values suit each industry, and why. The margin of safety uses only these.
METHODS = {
    "banks": (["graham_number", "graham_formula", "buffett"], "Lenders: book value is the anchor (Graham number), and Buffett's value counts only the profit a bank can pay out after funding loan growth."),
    "nbfc": (["graham_number", "graham_formula", "buffett"], "Lenders: book value is the anchor (Graham number), and Buffett's value counts only the profit that can be paid out after funding loan growth."),
    "insurance": (["graham_number", "buffett"], "Insurers: book value and distributable profit; the growth formula misleads because new policies depress early profit."),
    "it": (["graham_formula", "buffett"], "Asset-light, cash-rich businesses: the Graham number (which needs a large book value) understates them; value comes from earnings and owner earnings."),
    "fmcg": (["graham_formula", "buffett"], "Brand businesses with high returns on little capital: Buffett's owner-earnings value is the main measure; the Graham number understates them."),
    "pharma": (["graham_formula", "buffett"], "Value lies in products and approvals, not book assets: earnings-based values fit."),
    "consumer_durables": (["graham_formula", "buffett"], "Brand-led growers: earnings-based values fit better than book value."),
    "capital_goods": (["graham_formula", "buffett"], "Order-book driven: earnings and owner earnings fit; book value says little about engineering skill."),
    "metals": (["graham_number", "buffett"], "Cyclical: Graham's growth formula is not used (growth in a boom does not last); value rests on assets and cycle-average earnings."),
    "cement": (["graham_number", "buffett"], "Cyclical and asset-heavy: assets (Graham number) and cycle-average owner earnings; no growth extrapolation."),
    "oil_gas": (["graham_number", "buffett"], "Commodity-driven: assets and cycle-average cash flow; no growth extrapolation."),
    "chemicals": (["graham_number", "graham_formula", "buffett"], "Mix of commodity and specialty makers: all three, with cycle-average earnings."),
    "textiles": (["graham_number", "buffett"], "Cyclical, raw-material driven: assets and cycle-average cash flow."),
    "auto": (["graham_number", "graham_formula", "buffett"], "Cyclical consumer demand: all three on cycle-average earnings."),
    "power": (["graham_number", "buffett"], "Regulated returns on book value: the Graham number and steady owner earnings fit; growth comes from capacity, not margins."),
    "realty": (["graham_number"], "Developers book profit only on handover, so earnings and cash flows are lumpy: book value (Graham number) is the anchor."),
    "gold": (["graham_formula", "buffett"], "Branded jewellers grow with incomes: earnings-based values fit."),
    "capital_markets": (["graham_formula", "buffett"], "Asset-light, fee-based: earnings-based values fit."),
}
CYCLICAL = {"metals", "cement", "oil_gas", "textiles", "chemicals", "auto"}
DEFAULT_METHODS = (["graham_number", "graham_formula", "buffett"], "All three methods.")
GRAHAM_BASE_YIELD = 4.4
LONG_RUN_GROWTH = 4.0   # % a year after year 10, below the bond rate
MAX_GROWTH = 15.0       # Graham capped growth assumptions; so do we


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _cagr(new, old, n):
    if not new or not old or new <= 0 or old <= 0 or n <= 0:
        return None
    return ((new / old) ** (1 / n) - 1) * 100


def value(ys: list[dict], price: float | None, bond_yield: float | None, financial: bool, graham_checks: list[dict] | None = None,
          pe: float | None = None, pb: float | None = None, today=None, industry: str = "general") -> dict:
    """ys: statement years newest first (backend.app.statements.years). bond_yield: India 10-year G-sec, %.
    pe, pb: today's P/E and P/B from the data feed. Per-share figures are taken from them (EPS = price / P/E,
    book value per share = price / P/B), because they match today's share count; yearly statement EPS can
    be out of line after bonuses, splits, mergers or demergers."""
    if not ys:
        return {"available": False, "reason": "No published statements."}
    y = ys[0]
    from datetime import date as _d
    from .analysis import period_end
    end = period_end(y["period"])
    if end and (today or _d.today()).toordinal() - end.toordinal() > 550:
        return {"available": False, "reason": f"Latest statements are from {y['period']}: too old to value."}
    if price and pe and pe > 0:
        eps = round(price / pe, 2)
    else:
        eps = y.get("eps")
    bvps = round(price / pb, 2) if price and pb and pb > 0 else y.get("book_value_per_share")
    shares = round(y["equity"] / bvps, 3) if y.get("equity") and bvps and bvps > 0 else y.get("shares_cr")
    n = len(ys) - 1
    # Growth from total profit (not EPS), so share-count changes do not distort it
    g_hist = _cagr(y.get("pat"), ys[-1].get("pat"), n)
    g = max(0.0, min(MAX_GROWTH, g_hist)) if g_hist is not None else 0.0
    if industry in CYCLICAL:
        g = min(g, LONG_RUN_GROWTH)  # Graham: do not project a cyclical upswing forward
    Y = bond_yield or 7.0
    # Graham valued on normal earnings: scale today's EPS by the 3-year average profit over the latest year's
    pats = [x.get("pat") for x in ys[:3] if x.get("pat") is not None]
    normal = (sum(pats) / len(pats)) / y["pat"] if pats and y.get("pat") and y["pat"] > 0 else 1.0
    eps_n = round(eps * min(normal, 1.0), 2) if eps else eps  # never scale up
    flags = []
    suspect = pe is not None and 0 < pe < 4
    if suspect:
        flags.append(f"P/E of {pe} is unusually low: profit probably includes one-off gains, or the figures predate a demerger or share change. Check before relying on these values.")
    if normal < 0.7:
        flags.append("Latest profit is well above the 3-year average (possible one-off gain); Graham's values use the average.")
    out = {"available": True, "period": y["period"], "price": price, "flags": flags, "suspect": suspect, "inputs": {
        "EPS ₹ (price ÷ P/E)": eps, "normal EPS ₹ (3-yr average profit)": eps_n, "book value per share ₹ (price ÷ P/B)": bvps,
        f"profit growth a year ({n} yrs)": None if g_hist is None else round(g_hist, 1),
        "growth used %": round(g, 1), "bond yield %": round(Y, 2)}}

    # --- Graham
    gn = sqrt(22.5 * eps_n * bvps) if eps_n and bvps and eps_n > 0 and bvps > 0 else None
    gf = eps_n * (8.5 + 2 * g) * GRAHAM_BASE_YIELD / Y if eps_n and eps_n > 0 else None
    out["graham"] = {
        "number": round(gn, 2) if gn else None,
        "formula": round(gf, 2) if gf else None,
        "how": f"Graham number √(22.5 × EPS {eps_n} × book value {bvps}); Graham formula EPS {eps_n} × (8.5 + 2 × {g:.1f}) × 4.4 ÷ {Y:.2f}.",
        "checks": graham_checks or [],
    }

    # --- Buffett
    if financial:
        pat_avg = _avg([x.get("pat") for x in ys[:3]])
        base, base_label = None, "net profit"
    else:
        base = _avg([(x["cfo"] + x["cfi"]) for x in ys[:4] if x.get("cfo") is not None and x.get("cfi") is not None])
        base_label = f"owner earnings = operating + investing cash flow ({min(4, len(ys))}-yr average)"
    bv = None
    if financial:
        # Lenders: each year's cash to shareholders = profit x (1 - growth / ROE), the rest funds loan growth
        roe = y.get("roe_pct")
        if pat_avg and pat_avg > 0 and roe and roe > LONG_RUN_GROWTH and shares and Y > LONG_RUN_GROWTH:
            r, pv, earn = Y / 100, 0.0, pat_avg
            g0 = min(g, 0.9 * roe)
            for t in range(1, 11):
                gt = g0 + (LONG_RUN_GROWTH - g0) * (t - 1) / 9
                earn *= 1 + gt / 100
                pv += earn * max(0.0, 1 - gt / roe) / (1 + r) ** t
            tv = earn * (1 + LONG_RUN_GROWTH / 100) * (1 - LONG_RUN_GROWTH / roe) / (r - LONG_RUN_GROWTH / 100) / (1 + r) ** 10
            bv = (pv + tv) / shares
            base = pat_avg
            base_label = f"net profit (3-yr average), of which each year profit × (1 − growth ÷ ROE {roe:.1f}%) can be paid out; the rest funds loan growth"
    elif base and base > 0 and shares and Y > LONG_RUN_GROWTH:
        r, pv, cf = Y / 100, 0.0, base
        for t in range(1, 11):
            gt = g + (LONG_RUN_GROWTH - g) * (t - 1) / 9
            cf *= 1 + gt / 100
            pv += cf / (1 + r) ** t
        tv = cf * (1 + LONG_RUN_GROWTH / 100) / (r - LONG_RUN_GROWTH / 100) / (1 + r) ** 10
        bv = (pv + tv) / shares
    roes = [x.get("roe_pct") for x in ys if x.get("roe_pct") is not None]
    epss = [x.get("eps") for x in reversed(ys) if x.get("eps") is not None]
    fcfs = [x["cfo"] + x["cfi"] for x in ys if x.get("cfo") is not None and x.get("cfi") is not None]
    nms = [x.get("net_margin_pct") for x in ys if x.get("net_margin_pct") is not None]
    checks = [
        {"test": "Return on equity ≥ 15% every year", "pass": bool(roes) and min(roes) >= 15, "value": ", ".join(f"{r:.0f}%" for r in reversed(roes)) or "—"},
        {"test": "Earnings per share higher than 3 years earlier, rising in most years", "pass": len(epss) >= 3 and epss[-1] > epss[0] and sum(b > a for a, b in zip(epss, epss[1:])) >= len(epss) - 2,
         "value": " → ".join(f"{e:g}" for e in epss) or "—"},
    ]
    if not financial:
        checks.append({"test": "Positive owner earnings every year", "pass": bool(fcfs) and min(fcfs) > 0, "value": ", ".join(f"₹{f:,.0f} Cr" for f in reversed(fcfs)) or "—"})
        le = y.get("liabilities_to_equity")
        checks.append({"test": "Modest liabilities (total liabilities ≤ equity)", "pass": le is not None and le <= 1, "value": f"{le}×" if le is not None else "—"})
        checks.append({"test": "Net margin ≥ 10% (pricing power)", "pass": bool(nms) and nms[0] >= 10, "value": f"{nms[0]}%" if nms else "—"})
    else:
        checks.append({"test": "Return on assets ≥ 1% (lenders)", "pass": (y.get("roa_pct") or 0) >= 1, "value": f"{y.get('roa_pct')}%"})
    out["buffett"] = {"value": round(bv, 2) if bv else None, "base": round(base, 1) if base else None, "base_label": base_label,
                      "how": f"{base_label}: ₹{base:,.0f} Cr, growing {g:.1f}% a year fading to {LONG_RUN_GROWTH}% over 10 years, discounted at the {Y:.2f}% government bond rate, ÷ {shares} Cr shares."
                      if base and shares else "Not computed: owner earnings are negative or missing.",
                      "checks": checks, "passed": sum(c["pass"] for c in checks), "of": len(checks)}

    # --- Price against the values that suit this industry
    use, why = METHODS.get(industry, DEFAULT_METHODS)
    got = {"graham_number": out["graham"]["number"], "graham_formula": out["graham"]["formula"], "buffett": out["buffett"]["value"]}
    vals = [got[k] for k in use if got.get(k)]
    out["methods_used"] = use
    out["methods_why"] = why
    if price and vals:
        sv = sorted(vals)
        mid = sv[len(sv) // 2] if len(sv) % 2 else (sv[len(sv) // 2 - 1] + sv[len(sv) // 2]) / 2
        mos = (1 - price / mid) * 100
        out["value_mid"] = round(mid, 2)
        out["margin_of_safety_pct"] = round(mos, 1)
        out["reading"] = ("price well below value (margin of safety over 30%)" if mos >= 30 else "price below value" if mos >= 10 else
                          "price close to value" if mos > -10 else "price above value")
    # --- Greenblatt's Magic Formula inputs (ranked across all companies in build_value)
    nwc = (y.get("current_assets") or 0) - (y.get("current_liabilities") or 0) if y.get("current_assets") is not None else None
    cap = (max(nwc, 0) + y["non_current_assets"]) if nwc is not None and y.get("non_current_assets") else None
    ebit = y.get("pbt")
    out["magic"] = {"roc_pct": round(ebit / cap * 100, 1) if ebit is not None and cap else None,
                    "excluded": financial or industry == "power",
                    "how": "Return on capital = pre-tax profit ÷ (net working capital + long-term assets); earnings yield = 1 ÷ EV/EBITDA. "
                           "Interest and debt are not in the data feed, so pre-tax profit stands in for EBIT. Banks, lenders, insurers and utilities are left out, as in the book."}
    gp = [c for c in out["graham"]["checks"] if c.get("status") in ("pass", "fail", "partial")]
    out["graham"]["passed"] = sum(c["status"] == "pass" for c in gp)
    out["graham"]["of"] = len(gp)
    out["note"] = (f"Only {len(ys)} years of statements are in the data feed; Graham and Buffett looked at 10 years. "
                   "Owner earnings use operating + investing cash flow, so heavy expansion spending lowers them.")
    return out
