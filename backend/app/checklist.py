"""The owner's framework document as a checklist, answered from the numbers for every company.

Each item: section, question, answer (plain English, numbers inside), basis ("computed" from the
statements and market data, or "needs documents" where only an annual report, investor presentation or
con call can answer). Nothing is invented: when the data cannot answer, the item says so and names the
document that would."""


def _f(v, nd=1, suf=""):
    if v is None:
        return "n/a"
    return f"{v:,.{nd}f}{suf}"


def build(c: dict) -> list[dict]:
    """c: the assembled card (see backend/build_cards.py)."""
    st, vm, peer, prof = c.get("st") or {}, c.get("vm") or {}, c.get("peer") or {}, c.get("profile") or {}
    ys = st.get("years") or []
    y = ys[0] if ys else {}
    g = (vm.get("guide") or {})
    cyc = vm.get("cycle") or {}
    items = []

    def add(sec, q, a, basis="computed"):
        items.append({"s": sec, "q": q, "a": a, "b": basis})

    B = "Basic overview"
    desc = prof.get("description")
    add(B, "Value chain: where the company sits, and its competition",
        (desc[:600] + ("…" if len(desc) > 600 else "") if desc else "No business description in the data feed.")
        + f" Classified as {c.get('industry_label')} / {prof.get('sector') or 'n/a'}; {peer.get('n_peers', 'n/a')} listed companies in the same line of business; "
        + (f"the largest by revenue: {', '.join(peer.get('top', []))}." if peer.get("top") else ""),
        "computed + needs documents for the full value chain")
    if peer.get("industry_revenue_cr"):
        add(B, "Industry size and structure, number of players",
            f"Listed companies in {prof.get('sector') or c.get('industry_label')}: {peer['n_peers']}, combined revenue ₹{peer['industry_revenue_cr']:,.0f} Cr. "
            f"Top 3 hold {_f(peer.get('top3_share_pct'))}% of listed revenue; concentration (HHI) {_f(peer.get('hhi'), 0)} "
            f"({'concentrated' if (peer.get('hhi') or 0) > 2500 else 'moderately concentrated' if (peer.get('hhi') or 0) > 1500 else 'fragmented'}). "
            "Unlisted players and net imports are not in the data; see the industry report and ministry data.", "computed (listed companies) + needs documents (imports, unlisted)")
    at = [x.get("asset_turnover") for x in ys if x.get("asset_turnover") is not None]
    add(B, "Capacity utilisation: past, current, next 3 years",
        "Installed capacity and utilisation are disclosed only in the annual report or investor presentation. "
        + (f"Proxy from the statements: asset turnover (revenue ÷ assets) {' → '.join(_f(v, 2) for v in reversed(at))} over {len(at)} years"
           + (" — rising, so the asset base is being used harder." if len(at) > 1 and at[0] > at[-1] else " — falling, so new assets are not yet earning fully." if len(at) > 1 and at[0] < at[-1] else ".") if at else ""),
        "needs documents (proxy computed)")
    add(B, "Segments: high-margin low-volume vs low-margin high-volume",
        (f"Net margin {_f(y.get('net_margin_pct'))}% vs the industry median {_f(peer.get('median_net_margin'))}%, asset turnover {_f(y.get('asset_turnover'), 2)} vs {_f(peer.get('median_asset_turnover'), 2)}: "
         + ("higher margin, lower volume than peers." if (y.get('net_margin_pct') or 0) > (peer.get('median_net_margin') or 0) and (y.get('asset_turnover') or 0) < (peer.get('median_asset_turnover') or 0) else
            "lower margin, higher volume than peers." if (y.get('net_margin_pct') or 0) < (peer.get('median_net_margin') or 0) and (y.get('asset_turnover') or 0) > (peer.get('median_asset_turnover') or 0) else
            "better on both margin and asset use than peers." if (y.get('net_margin_pct') or 0) > (peer.get('median_net_margin') or 0) else "weaker on both than peers.")
         if y else "n/a") + " Segment revenue split: annual report segment note.", "computed + needs documents (segment split)")
    add(B, "Government policy: trade, taxes, subsidies",
        f"Effective tax rate {_f(y.get('tax_rate_pct'))}% in {y.get('period', 'n/a')}. Duties, subsidies and trade policy for the industry are covered in the industry report and economy drivers.",
        "needs documents")
    nca_share = (y.get("non_current_assets") or 0) / y["total_assets"] * 100 if y.get("total_assets") and y.get("non_current_assets") is not None else None
    add(B, "Nature and key driver of the business",
        f"{g.get('kind', 'n/a')}. Long-term assets are {_f(nca_share, 0)}% of total assets"
        + (" (capital intensive)" if nca_share and nca_share > 60 else " (asset light)" if nca_share is not None and nca_share < 35 else "")
        + f"; other income is {_f(y.get('other_income_share_pct'))}% of pre-tax profit. {g.get('why', '')}")
    add(B, "Cycle: current state and length",
        (f"{cyc['stage'][0].upper() + cyc['stage'][1:]}. " + " ".join(cyc.get("evidence", [])[:3]) + (" " + cyc["lynch"] if cyc.get("lynch") else "")
         if cyc.get("cyclical") else (cyc.get("note") or "Not a cyclical business."))
        + " Typical cycle length needs industry history (industry report).", "computed (position) + needs documents (length)")

    C = "Company specifics"
    add(C, "Market share",
        f"{_f(peer.get('revenue_share_pct'))}% of listed {prof.get('sector') or c.get('industry_label')} revenue, rank {peer.get('revenue_rank', 'n/a')} of {peer.get('n_peers', 'n/a')}. Share by product: annual report.",
        "computed (listed peers) + needs documents (by product)")
    add(C, "Strategy: mass, niche, cost leader or market-share player",
        (f"Revenue growth {_f(st.get('cagr', {}).get('revenue_pct'))}% a year vs industry median {_f(peer.get('median_revenue_cagr'))}%; net margin {_f(y.get('net_margin_pct'))}% vs {_f(peer.get('median_net_margin'))}%. "
         + ("Growing faster than peers at lower margins looks like a market-share strategy; " if (st.get('cagr', {}).get('revenue_pct') or 0) > (peer.get('median_revenue_cagr') or 0) and (y.get('net_margin_pct') or 0) < (peer.get('median_net_margin') or 0) else
            "Higher margins than peers suggest pricing power or a niche; " if (y.get('net_margin_pct') or 0) > (peer.get('median_net_margin') or 0) else "")
         + "management's stated strategy: investor presentation."), "computed + needs documents")
    if ys:
        add(C, "Ratios: margin, growth, return, leverage (history and next 2-3 years)",
            f"{len(ys)} years: revenue CAGR {_f(st['cagr'].get('revenue_pct'))}%, profit CAGR {_f(st['cagr'].get('pat_pct'))}%, EPS CAGR {_f(st['cagr'].get('eps_pct'))}%; "
            f"net margin {' → '.join(_f(x.get('net_margin_pct')) + '%' for x in reversed(ys))}; ROE {' → '.join(_f(x.get('roe_pct')) + '%' for x in reversed(ys))}; "
            f"liabilities ÷ equity {_f(y.get('liabilities_to_equity'), 2)}. "
            + (f"Trend projection: revenue {c['proj']['revenue_growth_pct']}% and profit {c['proj']['profit_growth_pct']}% a year (the recent trend, capped; not guidance)." if (c.get("proj") or {}).get("available") else ""))
    sh = c.get("sh") or {}
    ch = sh.get("change_over_period") or {}
    add(C, "Management image",
        f"From the numbers: promoter stake change over {len(sh.get('periods', []))} quarters {_f(ch.get('promoters'), 2, ' pts')}; share count change last year {_f(y.get('share_count_change_pct'))}%; "
        f"cash flow ÷ profit {_f(y.get('cfo_to_pat'), 2)}; tax rate {_f(y.get('tax_rate_pct'))}%. Governance, related-party deals and guidance track record: annual report and con calls. "
        "Pledged shares are not in the data feed.", "computed (signals) + needs documents")
    cfo = sum(x["cfo"] for x in ys if x.get("cfo") is not None)
    cfi = sum(x["cfi"] for x in ys if x.get("cfi") is not None)
    cff = sum(x["cff"] for x in ys if x.get("cff") is not None)
    roes = [x.get("roe_pct") for x in ys if x.get("roe_pct") is not None]
    add(C, "Capital allocation",
        f"Over {len(ys)} years: operating cash ₹{cfo:,.0f} Cr, invested ₹{-cfi:,.0f} Cr ({_f(-cfi / cfo * 100 if cfo > 0 else None, 0)}% of it), financing flow ₹{cff:,.0f} Cr. "
        + (f"ROE moved from {roes[-1]:.1f}% to {roes[0]:.1f}% while reinvesting, " + ("so reinvestment has earned well." if roes[0] >= roes[-1] else "so returns on new investment have been lower.") if len(roes) > 1 else "")
        + (f" Latest dividend: ₹{c['div']['amount']} ({c['div']['date']})." if c.get("div") else "")
        + " Acquisitions and buybacks: annual report.", "computed + needs documents")

    V = "Valuation"
    mt = st.get("multiples") or {}
    add(V, "Which valuation method suits this industry",
        f"{g.get('kind', 'n/a')}: main methods {', '.join(m['name'] for m in g.get('primary', []))}. Avoid: "
        + ("; ".join(f"{a['method']} ({a['why']})" for a in g.get("avoid", [])) or "none listed") + ".")
    meth = [m for m in vm.get("methods", []) if m.get("available")]
    add(V, "P/E, P/B, EV/EBITDA, EV/replacement, DCF",
        f"From the statements at ₹{_f(c.get('price'), 2)}: P/E {_f(mt.get('pe'))}, P/B {_f(mt.get('pb'), 2)}, P/S {_f(mt.get('ps'), 2)}, price ÷ operating cash {_f(mt.get('p_cfo'))}, "
        f"earnings yield {_f(mt.get('earnings_yield_pct'))}%, free-cash-flow yield {_f(mt.get('fcf_yield_pct'))}%, EV/EBITDA {_f(mt.get('ev_ebitda_upstox'))} (Upstox). "
        + " ".join(f"{m['name']}: {('₹' + format(m['value'], ',.2f') + ' (' + format(m['upside_pct'], '+.1f') + '% vs price)') if m.get('value') else m.get('reading', '')}." for m in meth)
        + (" EV/replacement cost needs installed capacity from the annual report." if any(m["id"] == "ev_replacement" for m in vm.get("methods", [])) else ""))
    hist = c.get("hist_mult") or {}
    add(V, "Historical valuation", (f"P/E now {_f(mt.get('pe'))} vs sector {_f(hist.get('pe_sector'))}; P/B {_f(mt.get('pb'), 2)} vs sector {_f(hist.get('pb_sector'), 2)}. "
                                    "Own 5-10 year valuation history needs year-end prices; see the stock's live analysis."), "computed (vs sector)")
    dcf = c.get("dcf") or {}
    add(V, "Intrinsic value with reasons",
        (f"{dcf.get('method')}: ₹{dcf['value']:,.2f} ({dcf['upside_pct']:+.1f}% vs price). {dcf.get('assumptions', '')}" if dcf.get("available") else dcf.get("reason", "n/a"))
        + (" " + vm["summary"] if vm.get("summary") else ""))

    O = "Other"
    rows = {r["key"]: r for r in sh.get("rows", [])}
    latest = lambda k: (rows[k]["values"][0]["pct"] if k in rows and rows[k]["values"] else None)  # noqa: E731
    add(O, "Shareholders", f"Promoters {_f(latest('promoters'), 2)}%, FII {_f(latest('fii'), 2)}%, mutual funds {_f(latest('mutual_funds'), 2)}%, other domestic institutions {_f(latest('other_dii'), 2)}%, retail {_f(latest('retail_and_other'), 2)}% "
        f"({(sh.get('periods') or ['n/a'])[0]}). Change over the period: " + ", ".join(f"{k} {v:+.2f} pts" for k, v in ch.items()) + ".")
    add(O, "Free float", f"{_f(c.get('free_float_pct'), 2)}% (100% − promoters).")
    add(O, "Index membership", ", ".join(c.get("indices") or []) or "Not in the NSE indices tracked.")
    dl = c.get("delivery") or {}
    add(O, "Volumes and deliveries", (f"Last session volume {dl['latest']['volume']:,}, delivery {dl['latest']['delivery_pct']}%; 5-day average delivery {dl['avg_delivery_pct']}%." if dl.get("available") else "Delivery data: NSE-listed stocks only."))
    add(O, "M&A possibility", "Needs news and filings (live analysis).", "needs documents")

    R = "Risk"
    flags = [x for x in st.get("checks", []) if x["flag"] in ("bad", "watch")]
    add(R, "Risks from the statements", " ".join(x["text"] for x in flags) or "No red flags in the statements.")
    alt = st.get("altman") or {}
    if alt.get("available"):
        add(R, "Balance-sheet stress (Altman Z'')", f"Z'' {alt['z']}: {alt['zone']}. {alt['note']}")
    add(R, "Risk mitigation", "Company's stated mitigation: annual report risk section.", "needs documents")

    M = "Magic Formula (Greenblatt)"
    mf = c.get("magic_formula") or {}
    add(M, "Return on capital and earnings yield",
        (f"Rank {mf['rank']} of {mf['of']} across the universe (ROCE {mf['roc']}%, earnings yield {mf['earnings_yield']}%)." if mf.get("rank") else mf.get("reason", "n/a")))
    pio = st.get("piotroski") or {}
    if pio.get("available"):
        add(M, "Piotroski F-score (financial strength)", f"{pio['score']} of {pio['of']} tests passed in {pio['period']}: {pio['reading']}.")
    return items
