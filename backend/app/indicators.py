"""The technical indicators that matter for a swing/positional read, computed on daily candles.

Trend: price vs 20/50/200-day averages and their slope, ADX(14) with +DI/-DI, Supertrend(10,3), Dow structure.
Momentum: RSI(14), MACD(12,26,9) histogram, 3- and 6-month return relative to the Nifty.
Volume: 20-day volume ratio, on-balance-volume trend. Volatility: ATR(14) %, Bollinger band width (squeeze).
Levels: distance to the 52-week high and to the nearest support/resistance (in ATRs)."""
from .charts import supertrend
from .technicals import analyse, atr, ema_series, rsi, sma


def adx(c: list[dict], n: int = 14) -> dict | None:
    if len(c) < n * 3:
        return None
    tr, pdm, ndm = [], [], []
    for a, b in zip(c, c[1:]):
        up, dn = b["high"] - a["high"], a["low"] - b["low"]
        pdm.append(up if up > dn and up > 0 else 0.0)
        ndm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(b["high"] - b["low"], abs(b["high"] - a["close"]), abs(b["low"] - a["close"])))
    def wilder(x):
        s = sum(x[:n]); out = [s]
        for v in x[n:]:
            s = s - s / n + v; out.append(s)
        return out
    atr_, p, m = wilder(tr), wilder(pdm), wilder(ndm)
    pdi = [100 * a / b if b else 0 for a, b in zip(p, atr_)]
    ndi = [100 * a / b if b else 0 for a, b in zip(m, atr_)]
    dx = [100 * abs(a - b) / (a + b) if a + b else 0 for a, b in zip(pdi, ndi)]
    adx_ = sum(dx[:n]) / n
    for v in dx[n:]:
        adx_ = (adx_ * (n - 1) + v) / n
    return {"adx": round(adx_, 1), "plus_di": round(pdi[-1], 1), "minus_di": round(ndi[-1], 1)}


def _ret(c, days):
    return (c[-1]["close"] / c[-1 - days]["close"] - 1) * 100 if len(c) > days else None


def compute(c: list[dict], nifty: list[dict] | None = None) -> dict:
    if len(c) < 60:
        return {"available": False}
    cl = [x["close"] for x in c]
    price = cl[-1]
    t = analyse(c, price)
    s20, s50, s200 = sma(cl, 20), sma(cl, 50), sma(cl, 200)
    s50_prev = sma(cl[:-20], 50) if len(cl) >= 70 else None
    s200_prev = sma(cl[:-20], 200) if len(cl) >= 220 else None
    e12, e26 = ema_series(cl, 12), ema_series(cl, 26)
    macd_line = [a - b for a, b in zip(e12, e26)]
    sig = ema_series(macd_line, 9)
    hist = macd_line[-1] - sig[-1]
    hist_prev = macd_line[-6] - sig[-6]
    _, st_dirs = supertrend(c)
    st_dir = st_dirs[-1]
    obv, o = [], 0
    for a, b in zip(c, c[1:]):
        o += b["volume"] if b["close"] > a["close"] else -b["volume"] if b["close"] < a["close"] else 0
        obv.append(o)
    obv_up = obv[-1] > (sum(obv[-20:]) / 20) if len(obv) >= 20 else None
    a14 = atr(c, 14)
    m20 = sum(cl[-20:]) / 20
    sd = (sum((x - m20) ** 2 for x in cl[-20:]) / 20) ** 0.5
    width = 4 * sd / m20 * 100
    widths = []
    for i in range(len(cl) - 120, len(cl)):
        if i >= 20:
            w = cl[i - 20:i]; mm = sum(w) / 20; ss = (sum((x - mm) ** 2 for x in w) / 20) ** 0.5
            widths.append(4 * ss / mm * 100)
    squeeze = bool(widths) and width <= sorted(widths)[len(widths) // 5]
    hi52 = max(x["high"] for x in c[-250:])
    rel = {}
    if nifty and len(nifty) > 130:
        nd = {x["date"]: x["close"] for x in nifty}
        for days, k in ((63, "rs_3m"), (126, "rs_6m")):
            if len(c) > days and c[-1 - days]["date"] in nd and c[-1]["date"] in nd:
                rel[k] = round(_ret(c, days) - (nd[c[-1]["date"]] / nd[c[-1 - days]["date"]] - 1) * 100, 1)
            elif len(c) > days:
                n_ret = _ret(nifty, days)
                rel[k] = round(_ret(c, days) - n_ret, 1) if n_ret is not None else None
    sup = t["supports"][0]["level"] if t.get("supports") else None
    res = t["resistances"][0]["level"] if t.get("resistances") else None
    return {
        "available": True, "price": price, "date": c[-1]["date"],
        "sma20": s20, "sma50": s50, "sma200": s200,
        "above_50": price > s50 if s50 else None, "above_200": price > s200 if s200 else None,
        "sma50_rising": (s50 > s50_prev) if s50 and s50_prev else None, "sma200_rising": (s200 > s200_prev) if s200 and s200_prev else None,
        "golden": (s50 > s200) if s50 and s200 else None,
        "adx": adx(c), "supertrend_up": st_dir == 1 if st_dir is not None else None,
        "rsi": rsi(cl, 14), "macd_hist": round(hist, 3), "macd_rising": hist > hist_prev,
        "ret_1m": round(_ret(c, 21), 1) if len(c) > 21 else None, "ret_3m": round(_ret(c, 63), 1) if len(c) > 63 else None,
        **rel,
        "volume_ratio": t.get("volume_ratio"), "obv_rising": obv_up,
        "atr_pct": round(a14 / price * 100, 2) if a14 else None, "bb_width_pct": round(width, 1), "squeeze": squeeze,
        "from_52w_high_pct": round((price / hi52 - 1) * 100, 1),
        "support": sup, "resistance": res,
        "to_support_atr": round((price - sup) / a14, 1) if sup and a14 else None,
        "to_resistance_atr": round((res - price) / a14, 1) if res and a14 else None,
        "extended_atr": round((price - s50) / a14, 1) if s50 and a14 else None,
    }


def score(x: dict) -> tuple[int | None, list[str], list[str]]:
    """0-100 technical strength with the reasons for and against (facts, no signal on its own)."""
    if not x.get("available"):
        return None, [], []
    pts, tot, pro, con = 0.0, 0.0, [], []

    def add(w, ok, yes, no):
        nonlocal pts, tot
        if ok is None:
            return
        tot += w
        if ok:
            pts += w
            if yes: pro.append(yes)
        elif no:
            con.append(no)

    add(2, x["above_200"], "above the 200-day average", "below the 200-day average")
    add(1.5, x["above_50"], "above the 50-day average", "below the 50-day average")
    add(1, x["sma50_rising"], "50-day average rising", "50-day average falling")
    add(1, x["golden"], "50-day above 200-day", None)
    a = x.get("adx") or {}
    if a:
        add(1.5, a["adx"] >= 20 and a["plus_di"] > a["minus_di"], f"ADX {a['adx']} with buyers in control (+DI {a['plus_di']} > −DI {a['minus_di']})",
            f"ADX {a['adx']}: " + ("sellers in control" if a["minus_di"] > a["plus_di"] else "no strong trend"))
    add(1, x["supertrend_up"], "Supertrend up", "Supertrend down")
    r = x.get("rsi")
    if r is not None:
        add(1, 50 <= r <= 70, f"RSI {r:.0f} (healthy momentum)", f"RSI {r:.0f}" + (" (overbought)" if r > 70 else " (weak momentum)"))
    add(1, x["macd_hist"] > 0 and x["macd_rising"], "MACD positive and rising", "MACD negative or fading")
    if x.get("rs_3m") is not None:
        add(1.5, x["rs_3m"] > 0, f"beating the Nifty by {x['rs_3m']:+.1f} pts over 3 months", f"lagging the Nifty by {x['rs_3m']:+.1f} pts over 3 months")
    add(0.5, x["obv_rising"], "on-balance volume rising (accumulation)", "on-balance volume falling")
    e = x.get("extended_atr")
    if e is not None and e > 4:
        con.append(f"stretched {e} ATRs above the 50-day average (chasing risk)")
        pts -= 0.75
    if x.get("squeeze"):
        pro.append("Bollinger squeeze: volatility compressed, a bigger move often follows")
    return (round(max(0, pts) / tot * 100) if tot else None), pro, con
