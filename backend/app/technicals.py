"""Technical analysis from daily candles: trend, momentum, volatility, volume, and support /
resistance levels, each with a plain-English reading. Pure functions; candles oldest first."""
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

    signals, score = [], 0.0

    def sig(text: str, weight: float):
        nonlocal score
        score += weight
        signals.append({"text": text, "effect": "bullish" if weight > 0 else "bearish" if weight < 0 else "neutral"})

    if s200:
        if price > s200:
            sig(f"Price is above its 200-day average (₹{s200}): long-term uptrend.", 1)
        else:
            sig(f"Price is below its 200-day average (₹{s200}): long-term downtrend.", -1)
    if s50 and s200:
        sig("50-day average is above the 200-day (golden-cross structure)." if s50 > s200
            else "50-day average is below the 200-day (death-cross structure).", 0.5 if s50 > s200 else -0.5)
    if s20:
        sig(f"Price {'above' if price > s20 else 'below'} its 20-day average (₹{s20}): short-term {'strength' if price > s20 else 'weakness'}.",
            0.5 if price > s20 else -0.5)
    if r is not None:
        if r >= 70:
            sig(f"RSI {r}: overbought; a pause or pullback is common from here.", -0.5)
        elif r <= 30:
            sig(f"RSI {r}: oversold; a bounce is common from here.", 0.5)
        elif r >= 55:
            sig(f"RSI {r}: healthy upward momentum.", 0.5)
        elif r <= 45:
            sig(f"RSI {r}: weak momentum.", -0.5)
        else:
            sig(f"RSI {r}: neutral momentum.", 0)
    if m:
        if m["crossed_up"]:
            sig("MACD just crossed above its signal line: fresh buy signal.", 1)
        elif m["crossed_down"]:
            sig("MACD just crossed below its signal line: fresh sell signal.", -1)
        else:
            sig(f"MACD is {'above' if m['histogram'] > 0 else 'below'} its signal line.", 0.5 if m["histogram"] > 0 else -0.5)
    if bb and bb["position_pct"] is not None:
        if bb["position_pct"] >= 100:
            sig("Closed above the upper Bollinger band: strong but stretched.", 0)
        elif bb["position_pct"] <= 0:
            sig("Closed below the lower Bollinger band: weak but stretched.", 0)
    if vol_ratio:
        if vol_ratio >= 1.5:
            day_up = closes[-1] >= closes[-2]
            sig(f"Volume {vol_ratio}× the 20-day average on an {'up' if day_up else 'down'} day: strong {'buying' if day_up else 'selling'}.",
                0.5 if day_up else -0.5)
    if price >= hi52 * 0.98:
        sig("Trading near its 52-week high: breakout territory.", 0.5)
    if price <= lo52 * 1.02:
        sig("Trading near its 52-week low.", -0.5)

    max_score = 5.5
    norm = max(-1, min(1, score / max_score))
    bias = "bullish" if norm >= 0.25 else "bearish" if norm <= -0.25 else "neutral"
    return {
        "available": True, "as_of": c[-1]["date"], "price": price,
        "moving_averages": {"sma20": s20, "sma50": s50, "sma200": s200},
        "rsi14": r, "macd": m, "atr14": a, "atr_pct": round(a / price * 100, 2) if a else None,
        "bollinger": bb, "volume_ratio": vol_ratio, "high_52w": hi52, "low_52w": lo52,
        "supports": sup, "resistances": res, "pivots": pivots(c[-1]),
        "signals": signals, "score": round(norm, 2), "bias": bias,
        "summary": f"Technical picture is {bias} ({len([s for s in signals if s['effect'] == 'bullish'])} bullish, "
                   f"{len([s for s in signals if s['effect'] == 'bearish'])} bearish signals).",
    }
