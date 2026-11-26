"""Intraday (15-minute and 30-minute) setups: map the chart, then say whether there is an entry point now.

For each timeframe: levels (previous day high/low/close, today's open, VWAP, CPR pivots, swing support and
resistance), indicators (EMA 20/50, RSI 14, MACD, ADX/DI, Supertrend, ATR, volume against its average), Dow
structure and chart/candle patterns. Then two standard setups are tested in each direction:

  Breakout  - a closed candle beyond a key level on above-average volume, momentum and trend strength behind it
  Pullback  - in an established intraday trend, price back at the 20 EMA / VWAP / support with a candle turning
              in the trend's direction

A setup is reported only with an entry zone, an invalidation (stop) level, targets at the next levels and a
reward-to-risk of at least 1.5. Otherwise the answer is "no entry now" with what would create one.
This is chart analysis for the owner, who decides and places trades himself. No position sizes."""
from datetime import datetime

from . import patterns, technicals
from .charts import supertrend
from .indicators import adx

MIN_RR = 1.5


def to_30m(c15: list[dict]) -> list[dict]:
    """Two 15-minute bars -> one 30-minute bar (session starts 09:15, so 09:15+09:30, 09:45+10:00, ...)."""
    out, cur = [], None
    for b in c15:
        hh, mm = int(b["t"][11:13]), int(b["t"][14:16])
        slot = ((hh * 60 + mm) - (9 * 60 + 15)) // 30
        key = (b["t"][:10], slot)
        if cur and cur["_k"] == key:
            cur.update(high=max(cur["high"], b["high"]), low=min(cur["low"], b["low"]), close=b["close"], volume=cur["volume"] + b["volume"])
        else:
            cur = {**b, "_k": key}
            out.append(cur)
    for x in out:
        x.pop("_k", None)
    return out


def to_60m(c15: list[dict]) -> list[dict]:
    """Four 15-minute bars -> one hourly bar (09:15-10:15, 10:15-11:15, ...)."""
    out, cur = [], None
    for b in c15:
        hh, mm = int(b["t"][11:13]), int(b["t"][14:16])
        key = (b["t"][:10], ((hh * 60 + mm) - (9 * 60 + 15)) // 60)
        if cur and cur["_k"] == key:
            cur.update(high=max(cur["high"], b["high"]), low=min(cur["low"], b["low"]), close=b["close"], volume=cur["volume"] + b["volume"])
        else:
            cur = {**b, "_k": key}
            out.append(cur)
    for x in out:
        x.pop("_k", None)
    return out


def to_period(daily: list[dict], kind: str) -> list[dict]:
    """Daily bars -> weekly ('W') or monthly ('M') bars, dated by their first session."""
    from datetime import date as _d
    out, cur = [], None
    for b in daily:
        d = _d.fromisoformat(b["date"][:10])
        key = d.isocalendar()[:2] if kind == "W" else (d.year, d.month)
        if cur and cur["_k"] == key:
            cur.update(high=max(cur["high"], b["high"]), low=min(cur["low"], b["low"]), close=b["close"], volume=cur["volume"] + (b.get("volume") or 0))
        else:
            cur = {"t": b["date"][:10] + "T09:15:00+05:30", "date": b["date"][:10], "open": b["open"], "high": b["high"], "low": b["low"],
                   "close": b["close"], "volume": b.get("volume") or 0, "_k": key}
            out.append(cur)
    for x in out:
        x.pop("_k", None)
    return out


TF_ORDER = [("m1", "1-min"), ("m5", "5-min"), ("m15", "15-min"), ("m30", "30-min"), ("h1", "1-hour"), ("d1", "daily"), ("w1", "weekly"), ("mo1", "monthly")]


def analyse_all(c1: list[dict], c5: list[dict], c15: list[dict], daily: list[dict], now: datetime | None = None) -> dict:
    """Every timeframe from 1 minute to monthly: the map and the entry verdict for each, and how they line up."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    live = (c1 or c15)[-1]["close"] if (c1 or c15) else None
    dbars = [{"t": d["date"][:10] + "T09:15:00+05:30", **d} for d in (daily or [])]
    today = now.date().isoformat()
    closed_d = [b for b in dbars if b["date"][:10] < today or now.hour * 60 + now.minute >= 15 * 60 + 30]
    wk, mo = to_period(dbars, "W"), to_period(dbars, "M")
    dt = None
    if len(dbars) >= 50:
        cl = [d["close"] for d in dbars]
        s20, s50 = sum(cl[-20:]) / 20, sum(cl[-50:]) / 50
        dt = "up" if cl[-1] > s20 > s50 else "down" if cl[-1] < s20 < s50 else "sideways"
    bars = {
        "m1": (_closed(c1, 1, now), False), "m5": (_closed(c5, 5, now), False), "m15": (_closed(c15, 15, now), False),
        "m30": (_closed(to_30m(c15), 30, now), False), "h1": (_closed(to_60m(c15), 60, now), False),
        "d1": (closed_d, True), "w1": (wk[:-1] if wk else wk, True), "mo1": (mo[:-1] if mo else mo, True),
    }
    out = {"daily_trend": dt, "live_price": live, "generated_at": now.isoformat(timespec="seconds"),
           "note": "Chart analysis only: entry zone, stop (where the setup is wrong) and targets at the next levels. You decide and place any trade yourself."}
    for k, label in TF_ORDER:
        c, htf = bars[k]
        out[k] = analyse_tf(c[-400:], label, dt, htf=htf) if c else {"available": False, "reason": "No candles."}
    # Early warning: the same test on the candle still forming (5-min to daily). It becomes an entry only if the
    # candle closes like this, so it is shown with the time the candle closes.
    forming_bars = {"m5": (c5, 5), "m15": (c15, 15), "m30": (to_30m(c15), 30), "h1": (to_60m(c15), 60)}
    if dbars and dbars[-1]["date"][:10] == today and not (now.hour * 60 + now.minute >= 15 * 60 + 30):
        forming_bars["d1"] = (dbars, None)
    from datetime import timedelta
    for k, (c, mins) in forming_bars.items():
        if not c or not out[k].get("available"):
            continue
        last = c[-1]
        start = datetime.fromisoformat(last["t"])
        closes = (start + timedelta(minutes=mins)) if mins else start.replace(hour=15, minute=30)
        if mins and k == "h1":  # the last hourly slot ends at 15:30
            closes = min(closes, start.replace(hour=15, minute=30))
        if closes.timestamp() <= now.timestamp():
            continue  # the candle has closed: it is in the normal analysis
        f = analyse_tf(c[-400:], dict(TF_ORDER)[k], dt, htf=(k == "d1"))
        fs = f.get("setup")
        if fs and not (out[k].get("setup") and out[k]["setup"]["direction"] == fs["direction"]):
            fs["closes_at"] = closes.strftime("%H:%M")
            fs["minutes_left"] = max(0, round((closes.timestamp() - now.timestamp()) / 60))
            out[k]["forming"] = fs
    # The 7 other timeframes must all agree before a setup counts as an entry point
    for k, label in TF_ORDER:
        a = out[k]
        f = a.get("forming") if a.get("available") else None
        if f:
            want = "up" if f["direction"] == "long" else "down"
            f["tf_checks"] = [{"tf": l2, "trend": (out[k2].get("trend") if out[k2].get("available") else None),
                               "ok": out[k2].get("available") and out[k2].get("trend") == want} for k2, l2 in TF_ORDER if k2 != k]
            f["tf_passed"] = sum(c["ok"] for c in f["tf_checks"])
            f["entry_if_closes"] = f["tf_passed"] == len(f["tf_checks"])
        s = a.get("setup") if a.get("available") else None
        if not s:
            continue
        want = "up" if s["direction"] == "long" else "down"
        checks = [{"tf": l2, "trend": (out[k2].get("trend") if out[k2].get("available") else None),
                   "ok": out[k2].get("available") and out[k2].get("trend") == want} for k2, l2 in TF_ORDER if k2 != k]
        n_ok = sum(c["ok"] for c in checks)
        s["tf_checks"] = checks
        s["tf_passed"] = n_ok
        s["entry"] = n_ok == len(checks)
        if not s["entry"]:
            failed = [f"{c['tf']} ({c['trend'] or 'n/a'})" for c in checks if not c["ok"]]
            a["verdict"] = (f"Setup forming ({s['direction']} {s['type'].lower()}) but NOT an entry: only {n_ok} of {len(checks)} other timeframes trend "
                            f"{want}. Not fulfilled: {', '.join(failed)}.")
        else:
            a["verdict"] = a["verdict"].replace("Entry point:", "Entry point (all 8 timeframes agree):", 1)
    # How the timeframes line up
    trends = {label: (out[k].get("trend") if out[k].get("available") else None) for k, label in TF_ORDER}
    ups = [l for l, t in trends.items() if t == "up"]
    downs = [l for l, t in trends.items() if t == "down"]
    found = [(label, out[k]["setup"]) for k, label in TF_ORDER if out[k].get("available") and (out[k].get("setup") or {}).get("entry")]
    out["alignment"] = {"trends": trends, "up": ups, "down": downs,
                        "summary": (f"Trend up on {', '.join(ups) or 'none'}; down on {', '.join(downs) or 'none'}. "
                                    + (f"Entry points (all timeframes agree) on: {', '.join(f'{l} ({s['direction']})' for l, s in found)}." if found else "No entry point with all 8 timeframes agreeing right now."))}
    out["combined"] = out["alignment"]["summary"]
    return out


def _ema(x, n):
    k, out, e = 2 / (n + 1), [], None
    for v in x:
        e = v if e is None else v * k + e * (1 - k)
        out.append(e)
    return out


def _rsi(cl, n=14):
    return technicals.rsi(cl, n)


def _vwap_today(c):
    d = c[-1]["t"][:10]
    pv = vol = 0.0
    for b in c:
        if b["t"][:10] == d:
            tp = (b["high"] + b["low"] + b["close"]) / 3
            pv += tp * b["volume"]
            vol += b["volume"]
    return pv / vol if vol else None


def _days(c):
    days = {}
    for b in c:
        d = b["t"][:10]
        x = days.setdefault(d, {"date": d, "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]})
        x.update(high=max(x["high"], b["high"]), low=min(x["low"], b["low"]), close=b["close"])
    return [days[k] for k in sorted(days)]


def analyse_tf(c: list[dict], tf: str, daily_trend: str | None = None, htf: bool = False) -> dict:
    """htf: daily/weekly/monthly bars (no VWAP; 'previous bar' instead of previous day; no session-time cautions)."""
    """Everything mapped on one timeframe, plus the setup verdict."""
    c = [b for b in c if b.get("volume") is not None]
    if len(c) < 60:
        return {"available": False, "reason": "Not enough intraday candles."}
    cl = [b["close"] for b in c]
    price = cl[-1]
    e20, e50 = _ema(cl, 20), _ema(cl, 50)
    macd_line = [a - b for a, b in zip(_ema(cl, 12), _ema(cl, 26))]
    sig = _ema(macd_line, 9)
    hist = [a - b for a, b in zip(macd_line, sig)]
    rsi = _rsi(cl)
    atr = technicals.atr(c, 14)
    ad = adx(c[-200:]) or {}
    _, st_dirs = supertrend(c)
    vol_avg = sum(b["volume"] for b in c[-21:-1]) / 20
    vol_ratio = round(c[-1]["volume"] / vol_avg, 2) if vol_avg else None
    vwap = None if htf else _vwap_today(c)
    if htf:
        days = [{"date": b["t"][:10], "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]} for b in c[-2:]]
    else:
        days = _days(c)
    prev = days[-2] if len(days) >= 2 else None
    today = days[-1]
    pname = "previous bar" if htf else "previous day"
    pivots = None
    if prev:
        p = (prev["high"] + prev["low"] + prev["close"]) / 3
        bc = (prev["high"] + prev["low"]) / 2
        tc = 2 * p - bc
        pivots = {"pivot": round(p, 2), "bc": round(min(bc, tc), 2), "tc": round(max(bc, tc), 2),
                  "r1": round(2 * p - prev["low"], 2), "s1": round(2 * p - prev["high"], 2),
                  "r2": round(p + prev["high"] - prev["low"], 2), "s2": round(p - (prev["high"] - prev["low"]), 2)}
    sw = technicals.swing_levels(c[-300:], price, window=3, lookback=300, tol=0.004)
    sup = sorted([l for l in sw if l["kind"] == "support"], key=lambda l: -l["level"])[:3]
    res = sorted([l for l in sw if l["kind"] == "resistance"], key=lambda l: l["level"])[:3]
    pat = patterns.detect(c[-200:], window=3, recent=30)
    cand = technicals.candle_patterns(c[-60:], last=3)

    # Every level that matters, with its name
    lv = []
    if prev:
        lv += [(prev["high"], f"{pname} high"), (prev["low"], f"{pname} low"), (prev["close"], "previous close")]
    lv += [(today["open"], "this bar's open" if htf else "today's open")]
    if vwap:
        lv.append((vwap, "VWAP"))
    if pivots:
        lv += [(pivots["r1"], "R1"), (pivots["s1"], "S1"), (pivots["r2"], "R2"), (pivots["s2"], "S2"), (pivots["pivot"], "pivot")]
    lv += [(l["level"], f"swing level ({l['touches']} touches)") for l in res + sup]
    for p_ in pat["patterns"]:
        lv.append((p_["breakout"], f"{p_['pattern']} breakout"))
        if p_.get("breakdown") is not None:
            lv.append((p_["breakdown"], f"{p_['pattern']} lower line"))
    lv = sorted({round(v, 2): n for v, n in lv if v}.items())
    above = [(v, n) for v, n in lv if v > price * 1.0005]
    below = [(v, n) for v, n in lv if v < price * 0.9995][::-1]

    ref = vwap if vwap else e20[-1]  # intraday: price vs VWAP; daily and above: price vs the 20 EMA
    up = e20[-1] > e50[-1] and price > ref
    down = e20[-1] < e50[-1] and price < ref
    dow = (pat.get("dow") or {}).get("trend", "")
    last, prevb = c[-1], c[-2]
    bull_candle = last["close"] > last["open"] or any(x["date"] == last["date"] and x["pattern"] in ("Hammer", "Bullish engulfing", "Morning star", "Bullish harami", "Piercing line") for x in cand)
    bear_candle = last["close"] < last["open"] or any(x["date"] == last["date"] and x["pattern"] in ("Shooting star", "Bearish engulfing", "Evening star", "Bearish harami", "Dark cloud cover") for x in cand)

    def setup(direction):
        long = direction == "long"
        sgn = 1 if long else -1
        reasons, kind = [], None
        # Breakout: the last closed candle crossed a key level
        crossed = [(v, n) for v, n in lv if (prevb["close"] <= v < last["close"]) if long] if long else \
                  [(v, n) for v, n in lv if (last["close"] < v <= prevb["close"])]
        if crossed and vol_ratio and vol_ratio >= 1.5 and ad.get("adx", 0) >= 20 and rsi and (55 <= rsi <= 75 if long else 25 <= rsi <= 45):
            lvl, name = crossed[-1] if long else crossed[0]
            kind = "Breakout"
            entry = (lvl, round(lvl + sgn * 0.3 * atr, 2))
            stop = round(lvl - sgn * 1.0 * atr, 2)
            reasons += [f"closed {'above' if long else 'below'} {name} ₹{lvl:,.2f}", f"volume {vol_ratio}× its average",
                        f"ADX {ad['adx']} ({'buyers' if ad['plus_di'] > ad['minus_di'] else 'sellers'} in control)", f"RSI {rsi:.0f}"]
        # Pullback in an established trend
        elif (up if long else down) and ("uptrend" in dow if long else "downtrend" in dow) and rsi and (40 <= rsi <= 62 if long else 38 <= rsi <= 60):
            near = [(abs(price - x) / atr, n, x) for x, n in ((e20[-1], "20 EMA"), (vwap, "VWAP")) if x] + \
                   [(abs(price - l["level"]) / atr, "swing support" if long else "swing resistance", l["level"]) for l in (sup if long else res)]
            near = [x for x in near if x[0] <= 0.5]
            if near and (bull_candle if long else bear_candle):
                kind = "Pullback"
                anchor = near[0]
                swings = [s for s in patterns.zigzag(c[-120:], 3) if s["type"] == ("low" if long else "high")]
                ref = swings[-1]["price"] if swings else price - sgn * atr
                entry = (round(price - sgn * 0.15 * atr, 2), round(price + sgn * 0.15 * atr, 2))
                stop = round(ref - sgn * 0.2 * atr, 2)
                if abs(price - stop) < 0.6 * atr:
                    stop = round(price - sgn * 0.8 * atr, 2)
                reasons += [f"intraday {'uptrend' if long else 'downtrend'} ({dow.split(':')[0]}; 20 EMA {'above' if long else 'below'} 50 EMA; price {'above' if long else 'below'} VWAP)",
                            f"pulled back to {anchor[1]} ₹{anchor[2]:,.2f}", f"last candle turned {'up' if long else 'down'}", f"RSI {rsi:.0f}"]
        if not kind:
            return None
        e_mid = (entry[0] + entry[1]) / 2
        risk = abs(e_mid - stop)
        if not risk or risk > 2.5 * atr:  # stop too far away for this timeframe: not a usable setup
            return None
        tgt_levels = [v for v, n in (above if long else below) if (v - e_mid) * sgn > 0.5 * risk]
        t1 = tgt_levels[0] if tgt_levels else round(e_mid + sgn * 2 * risk, 2)
        t2 = tgt_levels[1] if len(tgt_levels) > 1 else round(e_mid + sgn * 3 * risk, 2)
        if (t2 - t1) * sgn <= 0:  # the second target must lie beyond the first
            t2 = round(t1 + sgn * risk, 2)
        if t1 <= 0 or t2 <= 0:
            return None
        rr = round(abs(t1 - e_mid) / risk, 2) if risk else None
        conf = []
        if daily_trend:
            conf.append(("daily trend " + daily_trend, ("up" in daily_trend) == long))
        conf.append(("Supertrend " + ("up" if st_dirs[-1] == 1 else "down"), (st_dirs[-1] == 1) == long))
        conf.append(("MACD histogram " + ("rising" if hist[-1] > hist[-2] else "falling"), (hist[-1] > hist[-2]) == long))
        agree = sum(ok for _, ok in conf)
        return {"direction": direction, "type": kind, "entry_zone": [min(entry), max(entry)], "stop": stop,
                "targets": [round(t1, 2), round(t2, 2)], "reward_risk": rr, "reasons": reasons,
                "confirmations": [{"what": w, "agrees": ok} for w, ok in conf], "agree": agree, "of": len(conf),
                "valid": rr is not None and rr >= MIN_RR}

    setups = [s for s in (setup("long"), setup("short")) if s]
    good = [s for s in setups if s["valid"]]
    hhmm = c[-1]["t"][11:16]
    if good:
        best = max(good, key=lambda s: (s["agree"], s["reward_risk"]))
        verdict = (f"Entry point: {best['direction'].upper()} ({best['type'].lower()}) — entry ₹{best['entry_zone'][0]:,.2f}–₹{best['entry_zone'][1]:,.2f}, "
                   f"stop ₹{best['stop']:,.2f}, targets ₹{best['targets'][0]:,.2f} / ₹{best['targets'][1]:,.2f} (reward:risk {best['reward_risk']}), "
                   f"{best['agree']} of {best['of']} confirmations agree.")
    else:
        best = None
        nr = above[0] if above else None
        ns = below[0] if below else None
        wait = []
        if nr:
            wait.append(f"a {tf} close above {nr[1]} ₹{nr[0]:,.2f} on volume (breakout)")
        if ns:
            wait.append(f"a {tf} close below {ns[1]} ₹{ns[0]:,.2f} on volume (breakdown)")
        if up:
            wait.append(f"a pull back to the 20 EMA ₹{e20[-1]:,.2f}{'' if htf else ' / VWAP'} that holds (pullback entry)")
        elif down:
            wait.append(f"a bounce to the 20 EMA ₹{e20[-1]:,.2f}{'' if htf else ' / VWAP'} that fails (pullback short)")
        weak = [s for s in setups if not s["valid"]]
        verdict = ("No entry now" + (f": a {weak[0]['type'].lower()} {weak[0]['direction']} is forming but reward:risk is only {weak[0]['reward_risk']}" if weak else "")
                   + ". Wait for " + "; or ".join(wait) + ".")
    caution = []
    if not htf and hhmm < "09:30":
        caution.append("first 15 minutes: moves are noisy")
    if not htf and hhmm >= "15:00":
        caution.append("last 30 minutes of the session")
    if atr and price and atr / price * 100 < 0.15:
        caution.append("very low volatility: targets may not be reached")
    return {
        "available": True, "tf": tf, "as_of": (c[-1]["t"][:10] + " (bar start)") if htf else c[-1]["t"][:16].replace("T", " "), "price": price,
        "verdict": verdict, "setup": best, "setups": setups, "caution": caution,
        "trend": "up" if up else "down" if down else "sideways",
        "dow": dow + (f" — {(pat.get('dow') or {}).get('break')}" if (pat.get("dow") or {}).get("break") else ""),
        "ind": {"ema20": round(e20[-1], 2), "ema50": round(e50[-1], 2), "vwap": round(vwap, 2) if vwap else None, "rsi": round(rsi, 1) if rsi else None,
                "macd_hist": round(hist[-1], 3), "adx": ad, "supertrend": "up" if st_dirs[-1] == 1 else "down", "atr": round(atr, 2) if atr else None,
                "volume_ratio": vol_ratio},
        "htf": htf,
        "levels": {"above": [[v, n] for v, n in above[:6]], "below": [[v, n] for v, n in below[:6]], "pivots": pivots,
                   "prev_day": prev, "today_open": today["open"]},
        "patterns": pat["patterns"], "candles": [x for x in cand][-3:],
    }


def _closed(c: list[dict], minutes: int, now: datetime) -> list[dict]:
    """Only candles that have finished (the one still forming would give false signals)."""
    return [b for b in c if datetime.fromisoformat(b["t"]).timestamp() + minutes * 60 <= now.timestamp()]


def analyse(c15: list[dict], daily: list[dict] | None = None, now: datetime | None = None) -> dict:
    """15-minute and 30-minute analysis with a combined answer, on closed candles."""
    from zoneinfo import ZoneInfo
    now = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    live = c15[-1]["close"] if c15 else None
    c30 = _closed(to_30m(c15), 30, now)
    c15 = _closed(c15, 15, now)
    dt = None
    if daily and len(daily) >= 50:
        cl = [d["close"] for d in daily]
        s20, s50 = sum(cl[-20:]) / 20, sum(cl[-50:]) / 50
        dt = "up" if cl[-1] > s20 > s50 else "down" if cl[-1] < s20 < s50 else "sideways"
    a15 = analyse_tf(c15[-400:], "15-min", dt)
    a30 = analyse_tf(c30[-300:], "30-min", dt)
    s15, s30 = a15.get("setup"), a30.get("setup")
    if s15 and s30 and s15["direction"] == s30["direction"]:
        combined = f"15-min and 30-min agree: {s15['direction'].upper()} setup on both (stronger)."
    elif s15 or s30:
        s = s15 or s30
        other = a30 if s15 else a15
        combined = f"{'15' if s15 else '30'}-min {s['direction']} setup; the {'30' if s15 else '15'}-min chart trend is {other.get('trend', '—')}" + \
                   (" (agrees)." if other.get("trend") == ("up" if s["direction"] == "long" else "down") else " (does not confirm: weaker).")
    else:
        combined = "No entry on 15-min or 30-min right now."
    return {"daily_trend": dt, "m15": a15, "m30": a30, "combined": combined, "live_price": live,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "Chart analysis only: entry zone, stop (where the setup is wrong) and targets at the next levels. You decide and place any trade yourself."}
