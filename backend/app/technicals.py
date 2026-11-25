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


# ---------------------------------------------------------------- structure: swings, Fibonacci, trend lines

def swings(c: list[dict], window: int = 5) -> list[dict]:
    """Swing highs/lows (higher or lower than `window` bars on each side), oldest first."""
    out = []
    for i in range(window, len(c) - window):
        seg = c[i - window:i + window + 1]
        if c[i]["high"] == max(x["high"] for x in seg):
            out.append({"i": i, "date": c[i]["date"], "price": c[i]["high"], "type": "high"})
        if c[i]["low"] == min(x["low"] for x in seg):
            out.append({"i": i, "date": c[i]["date"], "price": c[i]["low"], "type": "low"})
    return out


def fibonacci(c: list[dict], lookback: int = 180) -> dict | None:
    """Retracements of the latest major move inside the lookback (from its extreme low to extreme high,
    in the order they happened), plus extensions beyond it."""
    seg = c[-lookback:]
    if len(seg) < 30:
        return None
    hi_i = max(range(len(seg)), key=lambda i: seg[i]["high"])
    lo_i = min(range(len(seg)), key=lambda i: seg[i]["low"])
    hi, lo = seg[hi_i]["high"], seg[lo_i]["low"]
    up = lo_i < hi_i  # the move ran upward (low first, then high)
    span = hi - lo
    if span <= 0:
        return None
    ratios = [0.236, 0.382, 0.5, 0.618, 0.786]
    levels = [{"ratio": r, "price": round(hi - span * r if up else lo + span * r, 2)} for r in ratios]
    ext = [{"ratio": r, "price": round(lo + span * r if up else hi - span * r, 2)} for r in (1.272, 1.618)]
    price = c[-1]["close"]
    retraced = (hi - price) / span if up else (price - lo) / span
    return {"direction": "up" if up else "down", "from": {"date": seg[lo_i if up else hi_i]["date"], "price": lo if up else hi},
            "to": {"date": seg[hi_i if up else lo_i]["date"], "price": hi if up else lo},
            "levels": levels, "extensions": ext, "retraced_pct": round(retraced * 100, 1),
            "reading": (f"The last major move was {'up' if up else 'down'} from ₹{(lo if up else hi):,.2f} to ₹{(hi if up else lo):,.2f}; "
                        f"price has retraced {retraced * 100:.0f}% of it.")}


def _line(p1: dict, p2: dict):
    slope = (p2["price"] - p1["price"]) / (p2["i"] - p1["i"])
    return slope, lambda i: p1["price"] + slope * (i - p1["i"])


def trend_lines(c: list[dict], lookback: int = 250, tol: float = 0.012) -> list[dict]:
    """Rising support lines through swing lows and falling resistance lines through swing highs.
    A line is kept only if no candle closes through it between its anchors and beyond, and it is
    confirmed by at least one more touch or is the most recent pair."""
    n = len(c)
    start = max(0, n - lookback)
    sw = [s for s in swings(c, 4) if s["i"] >= start]
    out = []
    for kind in ("low", "high"):
        pts = [s for s in sw if s["type"] == kind]
        best = None
        for a in range(len(pts) - 1):
            for b in range(a + 1, len(pts)):
                p1, p2 = pts[a], pts[b]
                if p2["i"] - p1["i"] < 10:
                    continue
                slope, f = _line(p1, p2)
                if (kind == "low" and slope <= 0) or (kind == "high" and slope >= 0):
                    continue
                broken = any((c[i]["close"] < f(i) * (1 - tol)) if kind == "low" else (c[i]["close"] > f(i) * (1 + tol))
                             for i in range(p1["i"], n))
                if broken:
                    continue
                touches = sum(1 for s in pts if s["i"] >= p1["i"] and abs(s["price"] / f(s["i"]) - 1) <= tol)
                score = touches * 10 + p2["i"] / n  # more touches, then more recent
                if best is None or score > best[0]:
                    best = (score, p1, p2, slope, f, touches)
        if best:
            _, p1, p2, slope, f, touches = best
            now = round(f(n - 1), 2)
            out.append({"kind": "rising support" if kind == "low" else "falling resistance",
                        "from": {"date": p1["date"], "price": round(p1["price"], 2), "bars_ago": n - 1 - p1["i"]},
                        "to": {"date": p2["date"], "price": round(p2["price"], 2), "bars_ago": n - 1 - p2["i"]},
                        "value_now": now, "touches": touches, "slope_per_day": round(slope, 3),
                        "distance_pct": round((c[-1]["close"] / now - 1) * 100, 1)})
    return out


# ---------------------------------------------------------------- candles and chart patterns

def candle_patterns(c: list[dict], last: int = 30) -> list[dict]:
    """Classic candlestick patterns in the last `last` sessions, with where they formed."""
    out = []
    start = max(3, len(c) - last)
    avg_body = mean(abs(x["close"] - x["open"]) for x in c[-60:]) or 1
    for i in range(start, len(c)):
        x, p, pp = c[i], c[i - 1], c[i - 2]
        o, h, l, cl = x["open"], x["high"], x["low"], x["close"]
        body, rng = abs(cl - o), (h - l) or 1e-9
        upper, lower = h - max(o, cl), min(o, cl) - l
        down_before = c[i - 3]["close"] > p["close"]
        up_before = c[i - 3]["close"] < p["close"]
        found = []
        if body <= 0.1 * rng:
            found.append(("Doji", "indecision"))
        if lower >= 2 * body and upper <= 0.3 * body + 0.1 * rng and body > 0 and down_before:
            found.append(("Hammer", "possible bottoming after a fall"))
        if upper >= 2 * body and lower <= 0.3 * body + 0.1 * rng and body > 0 and up_before:
            found.append(("Shooting star", "possible top after a rise"))
        pb = abs(p["close"] - p["open"])
        if cl > o and p["close"] < p["open"] and cl >= p["open"] and o <= p["close"] and body > pb:
            found.append(("Bullish engulfing", "buyers overwhelmed the previous day's sellers"))
        if cl < o and p["close"] > p["open"] and cl <= p["open"] and o >= p["close"] and body > pb:
            found.append(("Bearish engulfing", "sellers overwhelmed the previous day's buyers"))
        if h < p["high"] and l > p["low"]:
            found.append(("Inside bar", "range contraction; a breakout of the previous day's range often follows"))
        if p["close"] < p["open"] and body < pb * 0.5 and max(o, cl) < p["open"] and min(o, cl) > p["close"] and cl > o:
            found.append(("Bullish harami", "selling losing force"))
        if p["close"] > p["open"] and body < pb * 0.5 and max(o, cl) < p["close"] and min(o, cl) > p["open"] and cl < o:
            found.append(("Bearish harami", "buying losing force"))
        if body >= 1.8 * avg_body and upper <= 0.05 * rng and lower <= 0.05 * rng:
            found.append(("Bullish marubozu" if cl > o else "Bearish marubozu", "one side in full control all day"))
        ppb = abs(pp["close"] - pp["open"])
        if pp["close"] < pp["open"] and ppb > avg_body and pb < 0.5 * avg_body and cl > o and cl > (pp["open"] + pp["close"]) / 2:
            found.append(("Morning star", "three-candle reversal up"))
        if pp["close"] > pp["open"] and ppb > avg_body and pb < 0.5 * avg_body and cl < o and cl < (pp["open"] + pp["close"]) / 2:
            found.append(("Evening star", "three-candle reversal down"))
        if all(c[j]["close"] > c[j]["open"] and c[j]["close"] > c[j - 1]["close"] for j in (i - 2, i - 1, i)) and body > avg_body * 0.8:
            found.append(("Three white soldiers", "steady buying over three sessions"))
        if all(c[j]["close"] < c[j]["open"] and c[j]["close"] < c[j - 1]["close"] for j in (i - 2, i - 1, i)) and body > avg_body * 0.8:
            found.append(("Three black crows", "steady selling over three sessions"))
        if l > p["high"]:
            found.append(("Gap up", f"gap between ₹{p['high']:,.2f} and ₹{l:,.2f}"))
        if h < p["low"]:
            found.append(("Gap down", f"gap between ₹{h:,.2f} and ₹{p['low']:,.2f}"))
        for name, meaning in found:
            out.append({"date": x["date"], "i": i, "pattern": name, "meaning": meaning, "price": round(h if "Bear" in name or name in ("Shooting star", "Evening star", "Three black crows", "Gap down") else l, 2)})
    return out


def chart_patterns(c: list[dict]) -> list[dict]:
    """Double tops / bottoms among the last swings (two peaks or troughs within 2%, separated by a
    meaningful pullback), and whether the neckline has broken."""
    out = []
    sw = swings(c[-250:], 5)
    off = len(c) - len(c[-250:])
    highs = [s for s in sw if s["type"] == "high"][-4:]
    lows = [s for s in sw if s["type"] == "low"][-4:]
    for a, b in zip(highs, highs[1:]):
        if abs(a["price"] / b["price"] - 1) <= 0.02 and b["i"] - a["i"] >= 10:
            neck = min(x["low"] for x in c[off + a["i"]:off + b["i"] + 1])
            if (min(a["price"], b["price"]) - neck) / neck >= 0.03:
                out.append({"pattern": "Double top", "points": [a["date"], b["date"]], "level": round(max(a["price"], b["price"]), 2),
                            "neckline": round(neck, 2), "confirmed": c[-1]["close"] < neck,
                            "meaning": "two failed attempts at the same high" + ("; neckline broken" if c[-1]["close"] < neck else "; confirmed only if price closes below the neckline")})
    for a, b in zip(lows, lows[1:]):
        if abs(a["price"] / b["price"] - 1) <= 0.02 and b["i"] - a["i"] >= 10:
            neck = max(x["high"] for x in c[off + a["i"]:off + b["i"] + 1])
            if (neck - max(a["price"], b["price"])) / neck >= 0.03:
                out.append({"pattern": "Double bottom", "points": [a["date"], b["date"]], "level": round(min(a["price"], b["price"]), 2),
                            "neckline": round(neck, 2), "confirmed": c[-1]["close"] > neck,
                            "meaning": "two successful defences of the same low" + ("; neckline broken" if c[-1]["close"] > neck else "; confirmed only if price closes above the neckline")})
    # Keep recent patterns only, and mark ones the price has since invalidated
    recent_cut = c[-80]["date"] if len(c) >= 80 else c[0]["date"]
    kept = []
    for pt in out:
        if pt["points"][-1] < recent_cut:
            continue
        last = c[-1]["close"]
        if pt["pattern"] == "Double top" and last > pt["level"] * 1.01:
            pt.update(confirmed=False, meaning="double top invalidated: price has since risen above both peaks")
        if pt["pattern"] == "Double bottom" and last < pt["level"] * 0.99:
            pt.update(confirmed=False, meaning="double bottom failed: price has since fallen below both lows")
        kept.append(pt)
    return kept


def weekly_trend(c: list[dict]) -> dict:
    """Trend on weekly closes: higher highs/lows or lower highs/lows over the last swings."""
    weeks: dict[str, dict] = {}
    from datetime import date as _d
    for x in c:
        y, w, _ = _d.fromisoformat(x["date"]).isocalendar()
        k = f"{y}-{w:02d}"
        wk = weeks.setdefault(k, {"date": x["date"], "open": x["open"], "high": x["high"], "low": x["low"], "close": x["close"], "volume": 0})
        wk["high"], wk["low"], wk["close"], wk["date"] = max(wk["high"], x["high"]), min(wk["low"], x["low"]), x["close"], x["date"]
    wc = [weeks[k] for k in sorted(weeks)]
    sw = swings(wc, 2)
    hs = [s["price"] for s in sw if s["type"] == "high"][-3:]
    ls = [s["price"] for s in sw if s["type"] == "low"][-3:]
    if len(hs) >= 2 and len(ls) >= 2:
        if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
            t = "uptrend (higher highs and higher lows)"
        elif hs[-1] < hs[-2] and ls[-1] < ls[-2]:
            t = "downtrend (lower highs and lower lows)"
        else:
            t = "sideways / mixed (no clear sequence of highs and lows)"
    else:
        t = "not enough weekly swings"
    closes = [w["close"] for w in wc]
    return {"structure": t, "sma10w": sma(closes, 10), "sma40w": sma(closes, 40), "weeks": len(wc)}


def structure(c: list[dict]) -> dict:
    """Everything beyond indicators: Fibonacci, trend lines, candle and chart patterns, weekly trend."""
    window = c[-250:]
    return {"fibonacci": fibonacci(c), "trend_lines": trend_lines(c), "candles": candle_patterns(window),
            "chart_patterns": chart_patterns(c), "weekly": weekly_trend(c[-260 * 3:])}
