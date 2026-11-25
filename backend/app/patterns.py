"""Chart patterns from swing points, the way they are drawn by hand: Dow theory structure (HH/HL/LH/LL),
double and triple tops and bottoms (M and W), head and shoulders, triangles, wedges, rectangles and
channels, flags and pennants, cup and handle.

Each pattern carries the points and lines to draw, its breakout level, its status (forming / confirmed /
failed) and the textbook measured move (pattern height projected from the breakout), with what it
means in plain words. Mechanical detection: always check it by eye on the chart."""
from .technicals import swings


def zigzag(c: list[dict], window: int) -> list[dict]:
    """Alternating swing highs and lows (consecutive same-type swings collapsed to the extreme one)."""
    out: list[dict] = []
    for s in swings(c, window):
        if out and out[-1]["type"] == s["type"]:
            if (s["type"] == "high" and s["price"] >= out[-1]["price"]) or (s["type"] == "low" and s["price"] <= out[-1]["price"]):
                out[-1] = s
            continue
        out.append(s)
    return out


def _line_at(p1: dict, p2: dict, i: int) -> float:
    return p1["price"] + (p2["price"] - p1["price"]) * (i - p1["i"]) / (p2["i"] - p1["i"])


def _pt(s: dict) -> list:
    return [s["date"], round(s["price"], 2)]


def dow(c: list[dict], window: int = 5) -> dict:
    """Dow theory: label each swing against the previous one of its kind; trend = sequence of the last
    highs and lows; a close beyond the last opposite swing is a break of structure."""
    zz = zigzag(c, window)
    labels = []
    last = {"high": None, "low": None}
    for s in zz:
        prev = last[s["type"]]
        if prev is not None:
            tag = ("HH" if s["price"] > prev["price"] else "LH") if s["type"] == "high" else ("HL" if s["price"] > prev["price"] else "LL")
            labels.append({"date": s["date"], "price": round(s["price"], 2), "label": tag, "type": s["type"]})
        last[s["type"]] = s
    hs = [x for x in labels if x["type"] == "high"][-2:]
    ls = [x for x in labels if x["type"] == "low"][-2:]
    trend = "not enough swings"
    if hs and ls:
        h, l = hs[-1]["label"], ls[-1]["label"]
        trend = ("uptrend: higher highs and higher lows" if (h, l) == ("HH", "HL") else
                 "downtrend: lower highs and lower lows" if (h, l) == ("LH", "LL") else
                 "turning or sideways: " + ("a lower high after higher lows" if (h, l) == ("LH", "HL") else "a higher high after lower lows"))
    close = c[-1]["close"]
    brk = None
    if last["low"] and trend.startswith("uptrend") and close < last["low"]["price"]:
        brk = f"Close ₹{close:,.2f} is below the last higher low ₹{last['low']['price']:,.2f}: the uptrend's structure is broken (Dow: trend in doubt)."
    elif last["high"] and trend.startswith("downtrend") and close > last["high"]["price"]:
        brk = f"Close ₹{close:,.2f} is above the last lower high ₹{last['high']['price']:,.2f}: the downtrend's structure is broken."
    return {"trend": trend, "swings": labels[-12:], "break": brk,
            "last_swing_high": _pt(last["high"]) if last["high"] else None, "last_swing_low": _pt(last["low"]) if last["low"] else None}


def _status_up(close, level, fail):
    return "confirmed (closed above breakout)" if close > level else "failed" if close < fail else "forming"


def _status_down(close, level, fail):
    return "confirmed (closed below breakdown)" if close < level else "failed" if close > fail else "forming"


def _tops_bottoms(c, zz, out):
    close = c[-1]["close"]
    highs = [s for s in zz if s["type"] == "high"]
    lows = [s for s in zz if s["type"] == "low"]
    for kind, pts, opp in (("top", highs, lows), ("bottom", lows, highs)):
        for n in (3, 2):
            if len(pts) < n:
                continue
            grp = pts[-n:]
            ref = sum(p["price"] for p in grp) / n
            if any(abs(p["price"] / ref - 1) > 0.03 for p in grp) or grp[-1]["i"] - grp[0]["i"] < 10 * (n - 1):
                continue
            between = [o for o in opp if grp[0]["i"] < o["i"] < grp[-1]["i"]]
            if not between:
                continue
            neck = min(o["price"] for o in between) if kind == "top" else max(o["price"] for o in between)
            height = abs(ref - neck)
            if height / ref < 0.03:
                continue
            name = ("Triple " if n == 3 else "Double ") + kind + (" (M)" if kind == "top" and n == 2 else " (W)" if kind == "bottom" and n == 2 else "")
            if kind == "top":
                status = _status_down(close, neck, max(p["price"] for p in grp) * 1.01)
                target = neck - height
                meaning = f"{n} failed attempts near ₹{ref:,.2f}; a reversal lower is confirmed only on a close below the neckline ₹{neck:,.2f}."
            else:
                status = _status_up(close, neck, min(p["price"] for p in grp) * 0.99)
                target = neck + height
                meaning = f"{n} successful defences near ₹{ref:,.2f}; a reversal higher is confirmed only on a close above the neckline ₹{neck:,.2f}."
            out.append({"pattern": name, "bias": "bearish reversal" if kind == "top" else "bullish reversal",
                        "start": grp[0]["date"], "end": grp[-1]["date"], "points": [_pt(p) for p in grp] ,
                        "lines": [[[grp[0]["date"], round(neck, 2)], [c[-1]["date"], round(neck, 2)]]],
                        "breakout": round(neck, 2), "status": status, "measured_move": round(target, 2), "meaning": meaning})
            break  # a triple pattern replaces the double inside it


def _head_shoulders(c, zz, out):
    close, n = c[-1]["close"], len(c) - 1
    for inv in (False, True):
        main = [s for s in zz if s["type"] == ("low" if inv else "high")]
        opp = [s for s in zz if s["type"] == ("high" if inv else "low")]
        if len(main) < 3:
            continue
        l, h, r = main[-3:]
        sign = -1 if inv else 1
        if not (sign * (h["price"] - l["price"]) > 0.03 * h["price"] and sign * (h["price"] - r["price"]) > 0.03 * h["price"]):
            continue
        if abs(l["price"] / r["price"] - 1) > 0.06:
            continue
        t1 = [o for o in opp if l["i"] < o["i"] < h["i"]]
        t2 = [o for o in opp if h["i"] < o["i"] < r["i"]]
        if not t1 or not t2:
            continue
        a, b = t1[-1], t2[-1]
        neck_now = _line_at(a, b, n)
        height = abs(h["price"] - _line_at(a, b, h["i"]))
        if inv:
            status = _status_up(close, neck_now, r["price"] * 0.99)
            target = neck_now + height
        else:
            status = _status_down(close, neck_now, r["price"] * 1.01)
            target = neck_now - height
        out.append({"pattern": "Inverse head and shoulders" if inv else "Head and shoulders",
                    "bias": "bullish reversal" if inv else "bearish reversal", "start": l["date"], "end": r["date"],
                    "points": [_pt(l), _pt(h), _pt(r)], "lines": [[_pt(a), [c[-1]["date"], round(neck_now, 2)]]],
                    "breakout": round(neck_now, 2), "status": status, "measured_move": round(target, 2),
                    "meaning": f"Head at ₹{h['price']:,.2f} between shoulders at ₹{l['price']:,.2f} and ₹{r['price']:,.2f}; neckline now ₹{neck_now:,.2f}. "
                               + ("A close above the neckline confirms a turn up." if inv else "A close below the neckline confirms a turn down.")})


def _converging(c, zz, out, max_bars: int):
    """Triangles, wedges, rectangles and channels from the last two swing highs and two swing lows."""
    n, close = len(c) - 1, c[-1]["close"]
    recent = [s for s in zz if s["i"] >= n - max_bars]
    hs = [s for s in recent if s["type"] == "high"][-3:]
    ls = [s for s in recent if s["type"] == "low"][-3:]
    if len(hs) < 2 or len(ls) < 2:
        return
    h1, h2, l1, l2 = hs[0], hs[-1], ls[0], ls[-1]
    start = min(h1["i"], l1["i"])
    px = (h2["price"] + l2["price"]) / 2
    su = (h2["price"] - h1["price"]) / (h2["i"] - h1["i"]) / px * 100  # % per bar
    sl = (l2["price"] - l1["price"]) / (l2["i"] - l1["i"]) / px * 100
    up_now, lo_now = _line_at(h1, h2, n), _line_at(l1, l2, n)
    w_start, w_now = _line_at(h1, h2, start) - _line_at(l1, l2, start), up_now - lo_now
    if w_now <= 0 or w_start <= 0:
        return
    flat = 0.04
    conv = w_now < 0.75 * w_start
    if abs(su) < flat and sl > flat and conv:
        name, bias = "Ascending triangle", "usually bullish continuation"
    elif abs(sl) < flat and su < -flat and conv:
        name, bias = "Descending triangle", "usually bearish continuation"
    elif su < -flat and sl > flat and conv:
        name, bias = "Symmetrical triangle", "breaks either way; direction set by the breakout"
    elif su > 0 and sl > 0 and sl > su and conv:
        name, bias = "Rising wedge", "usually bearish (rally losing momentum)"
    elif su < 0 and sl < 0 and su < sl and conv:
        name, bias = "Falling wedge", "usually bullish (selling losing momentum)"
    elif abs(su) < flat and abs(sl) < flat:
        name, bias = "Rectangle (range)", "continuation or reversal; direction set by the breakout"
    elif su > flat and sl > flat and not conv:
        name, bias = "Rising channel", "uptrend inside parallel lines"
    elif su < -flat and sl < -flat and not conv:
        name, bias = "Falling channel", "downtrend inside parallel lines"
    else:
        return
    height = w_start
    if close > up_now:
        status, target = "broke out upward", up_now + height
    elif close < lo_now:
        status, target = "broke down", lo_now - height
    else:
        status, target = "forming (price inside the lines)", None
    out.append({"pattern": name, "bias": bias, "start": c[start]["date"], "end": c[-1]["date"],
                "points": [_pt(h1), _pt(h2), _pt(l1), _pt(l2)],
                "lines": [[_pt(h1), [c[-1]["date"], round(up_now, 2)]], [_pt(l1), [c[-1]["date"], round(lo_now, 2)]]],
                "breakout": round(up_now, 2), "breakdown": round(lo_now, 2), "status": status,
                "measured_move": None if target is None else round(target, 2),
                "meaning": f"Upper line now ₹{up_now:,.2f}, lower line ₹{lo_now:,.2f}. {bias[0].upper() + bias[1:]}."})


def _flags(c, out):
    """A sharp move (pole) followed by a short, shallow pause against it: flag (parallel) or pennant (converging)."""
    n = len(c)
    for pause in range(5, 21):
        if n < pause + 12:
            break
        body = c[n - pause:]
        pole_end = n - pause - 1
        for pole_len in (5, 8, 12):
            ps = pole_end - pole_len
            if ps < 0:
                continue
            p0, p1 = c[ps]["close"], c[pole_end]["close"]
            move = p1 / p0 - 1
            if abs(move) < 0.08:
                continue
            hi, lo = max(x["high"] for x in body), min(x["low"] for x in body)
            pole_h = abs(p1 - p0)
            up = move > 0
            retrace = ((p1 - lo) if up else (hi - p1)) / pole_h
            if retrace > 0.5 or (hi - lo) > 0.6 * pole_h:
                continue
            first, last = body[: len(body) // 2], body[len(body) // 2:]
            rng_first = max(x["high"] for x in first) - min(x["low"] for x in first)
            rng_last = max(x["high"] for x in last) - min(x["low"] for x in last)
            shape = "pennant" if rng_last < 0.6 * rng_first else "flag"
            close = c[-1]["close"]
            if up:
                status = "broke out upward" if close > max(x["high"] for x in body[:-1]) else "forming"
                target = hi + pole_h
            else:
                status = "broke down" if close < min(x["low"] for x in body[:-1]) else "forming"
                target = lo - pole_h
            out.append({"pattern": ("Bull " if up else "Bear ") + shape, "bias": "bullish continuation" if up else "bearish continuation",
                        "start": c[ps]["date"], "end": c[-1]["date"],
                        "points": [[c[ps]["date"], round(p0, 2)], [c[pole_end]["date"], round(p1, 2)]],
                        "lines": [[[body[0]["date"], round(hi, 2)], [c[-1]["date"], round(hi, 2)]], [[body[0]["date"], round(lo, 2)], [c[-1]["date"], round(lo, 2)]]],
                        "breakout": round(hi if up else lo, 2), "status": status, "measured_move": round(target, 2),
                        "meaning": f"A {abs(move) * 100:.0f}% {'rise' if up else 'fall'} in {pole_len} sessions, then a {pause}-session pause retracing {retrace * 100:.0f}% of it. "
                                   f"Continuation is confirmed on a {'close above ₹' + format(hi, ',.2f') if up else 'close below ₹' + format(lo, ',.2f')}."})
            return


def _cup(c, zz, out):
    """Cup and handle: a high, a rounded 12-35% decline and recovery to near that high, then a small pullback."""
    n, close = len(c) - 1, c[-1]["close"]
    highs = [s for s in zz if s["type"] == "high"]
    for a in reversed(highs[:-1]):
        later = [s for s in highs if s["i"] > a["i"] + 30]
        if not later:
            continue
        r = later[-1]
        if abs(r["price"] / a["price"] - 1) > 0.05:
            continue
        seg = c[a["i"]:r["i"] + 1]
        bottom = min(seg, key=lambda x: x["low"])
        depth = 1 - bottom["low"] / a["price"]
        bi = a["i"] + seg.index(bottom)
        if not 0.12 <= depth <= 0.35 or not (a["i"] + (r["i"] - a["i"]) * 0.25 <= bi <= a["i"] + (r["i"] - a["i"]) * 0.75):
            continue
        handle = c[r["i"]:]
        if not 3 <= len(handle) <= 25:
            continue
        hlow = min(x["low"] for x in handle)
        if 1 - hlow / r["price"] > 0.15 or hlow < bottom["low"] + (r["price"] - bottom["low"]) / 2:
            continue
        rim = max(a["price"], r["price"])
        out.append({"pattern": "Cup and handle", "bias": "bullish continuation", "start": a["date"], "end": c[-1]["date"],
                    "points": [_pt(a), [bottom["date"], round(bottom["low"], 2)], _pt(r)],
                    "lines": [[_pt(a), [c[-1]["date"], round(rim, 2)]]], "breakout": round(rim, 2),
                    "status": "broke out upward" if close > rim else "forming (handle)", "measured_move": round(rim + (rim - bottom["low"]), 2),
                    "meaning": f"Cup {depth * 100:.0f}% deep from ₹{a['price']:,.2f} to ₹{bottom['low']:,.2f} and back; handle pullback to ₹{hlow:,.2f}. Confirmed on a close above the rim ₹{rim:,.2f}."})
        return


def detect(c: list[dict], window: int = 5, recent: int = 60) -> dict:
    """All patterns on one timeframe. `recent`: keep patterns that ended within this many bars."""
    if len(c) < 40:
        return {"dow": None, "patterns": []}
    zz = zigzag(c, window)
    out: list[dict] = []
    _tops_bottoms(c, zz, out)
    _head_shoulders(c, zz, out)
    _converging(c, zz, out, max_bars=recent * 2)
    _flags(c, out)
    _cup(c, zz, out)
    cut = c[-recent]["date"] if len(c) > recent else c[0]["date"]
    out = [p for p in out if p["end"] >= cut and p["status"] != "failed"]
    close = c[-1]["close"]
    kept = []
    for p in out:  # drop ranges the price left long ago (broke out by more than 1.5x the pattern's own height)
        if p.get("breakdown") is not None:
            h = p["breakout"] - p["breakdown"]
            if h > 0 and (close > p["breakout"] + 1.5 * h or close < p["breakdown"] - 1.5 * h):
                continue
        kept.append(p)
    out = kept
    return {"dow": dow(c, window), "patterns": out,
            "note": "Found mechanically from swing highs and lows; check each by eye. Measured move = the textbook projection of the pattern's height from its breakout, not a forecast."}
