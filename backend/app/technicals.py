"""Chart facts from daily candles: moving averages, momentum, volatility, volume, and support /
resistance levels. Facts only, no buy/sell signals. Pure functions; candles oldest first."""
from statistics import mean, pstdev


def sma(x: list[float], n: int) -> float | None:
    return round(mean(x[-n:]), 2) if len(x) >= n else None


def ema_series(x: list[float], n: int) -> list[float]:
    if not x:
        return []
    k, out = 2 / (n + 1), [x[0]]
    for v in x[1:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def rsi(closes: list[float], n: int = 14) -> float | None:
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]
    ag, al = mean(gains[:n]), mean(losses[:n])
    for g, l in zip(gains[n:], losses[n:]):  # Wilder smoothing
        ag, al = (ag * (n - 1) + g) / n, (al * (n - 1) + l) / n
    return 100.0 if al == 0 else round(100 - 100 / (1 + ag / al), 1)


def macd(closes: list[float]) -> dict | None:
    if len(closes) < 35:
        return None
    line = [a - b for a, b in zip(ema_series(closes, 12), ema_series(closes, 26))]
    signal = ema_series(line, 9)
    hist = [a - b for a, b in zip(line, signal)]
    return {"macd": round(line[-1], 2), "signal": round(signal[-1], 2), "histogram": round(hist[-1], 2),
            "crossed_up": hist[-1] > 0 >= hist[-2], "crossed_down": hist[-1] < 0 <= hist[-2]}


def atr(c: list[dict], n: int = 14) -> float | None:
    if len(c) <= n:
        return None
    trs = [max(c[i]["high"] - c[i]["low"], abs(c[i]["high"] - c[i - 1]["close"]), abs(c[i]["low"] - c[i - 1]["close"]))
           for i in range(1, len(c))]
    a = mean(trs[:n])
    for t in trs[n:]:
        a = (a * (n - 1) + t) / n
    return round(a, 2)


def bollinger(closes: list[float], n: int = 20, k: float = 2) -> dict | None:
    if len(closes) < n:
        return None
    m, sd = mean(closes[-n:]), pstdev(closes[-n:])
    up, lo = m + k * sd, m - k * sd
    return {"upper": round(up, 2), "middle": round(m, 2), "lower": round(lo, 2),
            "position_pct": round((closes[-1] - lo) / (up - lo) * 100) if up > lo else None,
            "width_pct": round((up - lo) / m * 100, 1)}


def swing_levels(c: list[dict], price: float, window: int = 5, lookback: int = 250, tol: float = 0.015) -> list[dict]:
    """Support/resistance from swing highs and lows (a bar higher/lower than `window` bars each side),
    clustered when within `tol` of each other. More touches = stronger level."""
    c = c[-lookback:]
    pts = []
    for i in range(window, len(c) - window):
        hi = c[i]["high"]
        lo = c[i]["low"]
        if all(hi >= c[j]["high"] for j in range(i - window, i + window + 1)):
            pts.append((hi, c[i]["date"]))
        if all(lo <= c[j]["low"] for j in range(i - window, i + window + 1)):
            pts.append((lo, c[i]["date"]))
    pts.sort()
    clusters: list[list[tuple[float, str]]] = []
    for p in pts:
        if clusters and abs(p[0] / mean(q[0] for q in clusters[-1]) - 1) <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = []
    for cl in clusters:
        lvl = round(mean(p[0] for p in cl), 2)
        levels.append({"level": lvl, "touches": len(cl), "last_touch": max(p[1] for p in cl),
                       "kind": "support" if lvl < price else "resistance",
                       "distance_pct": round((lvl / price - 1) * 100, 1)})
    return levels


def pivots(last: dict) -> dict:
    """Classic floor-trader pivots from the last completed day."""
    p = (last["high"] + last["low"] + last["close"]) / 3
    r = lambda v: round(v, 2)  # noqa: E731
    return {"pivot": r(p), "r1": r(2 * p - last["low"]), "s1": r(2 * p - last["high"]),
            "r2": r(p + last["high"] - last["low"]), "s2": r(p - (last["high"] - last["low"])), "from_date": last["date"]}


def analyse(c: list[dict], price: float | None = None) -> dict:
    if len(c) < 60:
        return {"available": False, "reason": "Less than 60 days of price history."}
    closes = [x["close"] for x in c]
    price = price or closes[-1]
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    r = rsi(closes)
    m = macd(closes)
    a = atr(c)
    bb = bollinger(closes)
    vols = [x["volume"] for x in c if x["volume"]]
    vol_ratio = round(vols[-1] / mean(vols[-21:-1]), 2) if len(vols) > 21 and mean(vols[-21:-1]) else None
    lv = swing_levels(c, price)
    sup = sorted([l for l in lv if l["kind"] == "support"], key=lambda l: -l["level"])[:3]
    res = sorted([l for l in lv if l["kind"] == "resistance"], key=lambda l: l["level"])[:3]
    year = c[-250:]
    hi52, lo52 = max(x["high"] for x in year), min(x["low"] for x in year)

    obs = []  # plain facts, no buy/sell reading
    if s200:
        obs.append(f"Price is {abs(price / s200 - 1) * 100:.1f}% {'above' if price > s200 else 'below'} its 200-day average (₹{s200}).")
    if s50 and s200:
        obs.append(f"50-day average (₹{s50}) is {'above' if s50 > s200 else 'below'} the 200-day average.")
    if s20:
        obs.append(f"Price is {abs(price / s20 - 1) * 100:.1f}% {'above' if price > s20 else 'below'} its 20-day average (₹{s20}).")
    if r is not None:
        obs.append(f"RSI is {r}" + (" (above 70, historically stretched)." if r >= 70 else " (below 30, historically stretched)." if r <= 30 else "."))
    if m and (m["crossed_up"] or m["crossed_down"]):
        obs.append(f"MACD crossed {'above' if m['crossed_up'] else 'below'} its signal line on the last day.")
    if bb and bb["position_pct"] is not None and (bb["position_pct"] >= 100 or bb["position_pct"] <= 0):
        obs.append(f"Closed {'above the upper' if bb['position_pct'] >= 100 else 'below the lower'} Bollinger band.")
    if vol_ratio:
        obs.append(f"Last day's volume was {vol_ratio}× the 20-day average.")
    obs.append(f"52-week range ₹{lo52:,.2f} – ₹{hi52:,.2f}; price is {(price / hi52 - 1) * 100:.1f}% from the high.")
    return {
        "available": True, "as_of": c[-1]["date"], "price": price,
        "moving_averages": {"sma20": s20, "sma50": s50, "sma200": s200},
        "rsi14": r, "macd": m, "atr14": a, "atr_pct": round(a / price * 100, 2) if a else None,
        "bollinger": bb, "volume_ratio": vol_ratio, "high_52w": hi52, "low_52w": lo52,
        "supports": sup, "resistances": res, "pivots": pivots(c[-1]),
        "observations": obs,
        "note": "Chart facts only. They are one input among many and are read together with the business, the economy, news and positioning.",
    }
