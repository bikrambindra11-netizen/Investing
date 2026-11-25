"""Multi-timeframe chart data: candles for any timeframe (1 minute to monthly) plus every overlay the
chart draws — moving averages, VWAP, Supertrend, Bollinger bands, RSI, MACD, support/resistance,
Fibonacci, trend lines, pivots, candle and chart patterns, and market structure.

Facts for the chart; nothing here is a buy/sell signal."""
import time
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from . import technicals as T

IST = ZoneInfo("Asia/Kolkata")
BASE = "https://api.upstox.com/v3/historical-candle"

# tf: (unit, interval, history days, cache seconds, moving averages)
TIMEFRAMES = {
    "1m": ("minutes", 1, 5, 20, [("EMA", 9), ("EMA", 21)]),
    "5m": ("minutes", 5, 20, 30, [("EMA", 9), ("EMA", 21), ("EMA", 50)]),
    "15m": ("minutes", 15, 30, 45, [("EMA", 20), ("EMA", 50), ("EMA", 200)]),
    "30m": ("minutes", 30, 85, 60, [("EMA", 20), ("EMA", 50), ("EMA", 200)]),
    "1h": ("hours", 1, 85, 60, [("EMA", 20), ("EMA", 50), ("EMA", 200)]),
    "1D": ("days", 1, 365 * 3, 300, [("SMA", 20), ("SMA", 50), ("SMA", 200)]),
    "1W": ("weeks", 1, 365 * 10, 1800, [("SMA", 10), ("SMA", 40)]),
    "1M": ("months", 1, 365 * 26, 3600, [("SMA", 12), ("SMA", 24)]),
}
INTRADAY = {"1m", "5m", "15m", "30m", "1h"}
_cache: dict[tuple, tuple[float, list]] = {}


def _get(url: str) -> list[list]:
    for attempt in range(3):
        try:
            r = httpx.get(url, headers={"Accept": "application/json"}, timeout=25)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return (r.json().get("data") or {}).get("candles") or []
        except httpx.HTTPError:
            time.sleep(1)
    return []


def _to_rows(raw: list[list]) -> list[dict]:
    rows = [{"t": x[0], "open": x[1], "high": x[2], "low": x[3], "close": x[4], "volume": x[5] or 0} for x in raw]
    rows.sort(key=lambda r: r["t"])
    for r in rows:
        r["date"] = r["t"][:10] if len(r["t"]) <= 10 or r["t"][11:16] == "00:00" else r["t"][:16].replace("T", " ")
        r["time"] = int(datetime.fromisoformat(r["t"]).timestamp())
    return rows


def _aggregate_today(intraday: list[dict], tf: str) -> dict | None:
    """Today's daily/weekly/monthly bar from today's intraday candles (Upstox's daily history lags)."""
    if not intraday:
        return None
    d0 = intraday[0]["t"][:10]
    return {"t": d0 + "T00:00:00+05:30", "open": intraday[0]["open"], "high": max(x["high"] for x in intraday),
            "low": min(x["low"] for x in intraday), "close": intraday[-1]["close"], "volume": sum(x["volume"] for x in intraday)}


def candles(key: str, tf: str) -> list[dict]:
    unit, n, days, ttl, _ = TIMEFRAMES[tf]
    hit = _cache.get((key, tf))
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    k = quote(key, safe="")
    today = datetime.now(IST).date()
    hist = _get(f"{BASE}/{k}/{unit}/{n}/{today.isoformat()}/{(today - timedelta(days=days)).isoformat()}")
    rows = {r[0]: r for r in hist}
    if tf in INTRADAY:
        for r in _get(f"{BASE}/intraday/{k}/{unit}/{n}"):
            rows[r[0]] = r
        out = _to_rows(list(rows.values()))
    else:
        out = _to_rows(list(rows.values()))
        today_rows = _to_rows(_get(f"{BASE}/intraday/{k}/minutes/30"))
        bar = _aggregate_today(today_rows, tf)
        if bar and out:
            last = out[-1]
            if tf == "1D" and bar["t"][:10] > last["t"][:10]:
                out += _to_rows([[bar["t"], bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]]])
            elif tf in ("1W", "1M") and bar["t"][:10] > last["t"][:10]:
                same = (date.fromisoformat(bar["t"][:10]).isocalendar()[:2] == date.fromisoformat(last["t"][:10]).isocalendar()[:2]) \
                    if tf == "1W" else bar["t"][:7] == last["t"][:7]
                if same:  # extend the current week/month with today
                    last.update(high=max(last["high"], bar["high"]), low=min(last["low"], bar["low"]), close=bar["close"],
                                volume=last["volume"] + bar["volume"])
    _cache[(key, tf)] = (time.time(), out)
    return out


# ---------------------------------------------------------------- series indicators

def sma_series(x, n):
    out, s = [], 0.0
    for i, v in enumerate(x):
        s += v
        if i >= n:
            s -= x[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def ema_full(x, n):
    out, e = [], None
    k = 2 / (n + 1)
    for i, v in enumerate(x):
        e = v if e is None else v * k + e * (1 - k)
        out.append(e if i >= n - 1 else None)
    return out


def rsi_series(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    g = [max(c[i] - c[i - 1], 0) for i in range(1, len(c))]
    l_ = [max(c[i - 1] - c[i], 0) for i in range(1, len(c))]
    ag, al = sum(g[:n]) / n, sum(l_[:n]) / n
    out[n] = 100 - 100 / (1 + ag / al) if al else 100
    for i in range(n, len(g)):
        ag, al = (ag * (n - 1) + g[i]) / n, (al * (n - 1) + l_[i]) / n
        out[i + 1] = 100 - 100 / (1 + ag / al) if al else 100
    return out


def macd_series(c):
    e12, e26 = ema_full(c, 12), ema_full(c, 26)
    line = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    vals = [v for v in line if v is not None]
    sig_vals = ema_full(vals, 9)
    sig = [None] * (len(line) - len(vals)) + sig_vals
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig)]
    return line, sig, hist


def bollinger_series(c, n=20, k=2):
    up, lo = [], []
    for i in range(len(c)):
        if i < n - 1:
            up.append(None)
            lo.append(None)
            continue
        w = c[i - n + 1:i + 1]
        m = sum(w) / n
        sd = (sum((v - m) ** 2 for v in w) / n) ** 0.5
        up.append(m + k * sd)
        lo.append(m - k * sd)
    return up, lo


def vwap_series(rows):
    """Session VWAP, restarting each trading day."""
    out, day, pv, vv = [], None, 0.0, 0.0
    for r in rows:
        d = r["t"][:10]
        if d != day:
            day, pv, vv = d, 0.0, 0.0
        tp = (r["high"] + r["low"] + r["close"]) / 3
        pv += tp * r["volume"]
        vv += r["volume"]
        out.append(pv / vv if vv else None)
    return out


def supertrend(rows, n=10, mult=3.0):
    """Supertrend line and direction (1 = price above the line, -1 = below)."""
    if len(rows) <= n:
        return [None] * len(rows), [None] * len(rows)
    tr = [rows[0]["high"] - rows[0]["low"]] + [max(r["high"] - r["low"], abs(r["high"] - p["close"]), abs(r["low"] - p["close"]))
                                              for p, r in zip(rows, rows[1:])]
    atr = [None] * len(rows)
    atr[n - 1] = sum(tr[:n]) / n
    for i in range(n, len(rows)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    line, dirs = [None] * len(rows), [None] * len(rows)
    fu = fl = None
    d = 1
    for i in range(n - 1, len(rows)):
        mid = (rows[i]["high"] + rows[i]["low"]) / 2
        bu, bl = mid + mult * atr[i], mid - mult * atr[i]
        pc = rows[i - 1]["close"] if i else rows[i]["close"]
        fu = bu if fu is None or bu < fu or pc > fu else fu
        fl = bl if fl is None or bl > fl or pc < fl else fl
        if d == 1 and rows[i]["close"] < fl:
            d = -1
        elif d == -1 and rows[i]["close"] > fu:
            d = 1
        line[i], dirs[i] = (fl if d == 1 else fu), d
    return line, dirs


def market_structure(rows, window):
    sw = T.swings(rows, window)
    hs = [s["price"] for s in sw if s["type"] == "high"][-3:]
    ls = [s["price"] for s in sw if s["type"] == "low"][-3:]
    if len(hs) >= 2 and len(ls) >= 2:
        if hs[-1] > hs[-2] and ls[-1] > ls[-2]:
            return "uptrend: higher highs and higher lows"
        if hs[-1] < hs[-2] and ls[-1] < ls[-2]:
            return "downtrend: lower highs and lower lows"
        return "range / mixed: highs and lows not in sequence"
    return "not enough swings yet"


def chart(key: str, tf: str, bars: int | None = None) -> dict:
    rows = candles(key, tf)
    if not rows:
        return {"tf": tf, "candles": [], "error": "No price data for this timeframe."}
    unit, n, days, ttl, mas = TIMEFRAMES[tf]
    closes = [r["close"] for r in rows]
    price = closes[-1]
    window = {"1m": 5, "5m": 5, "15m": 5, "30m": 4, "1h": 4, "1D": 5, "1W": 3, "1M": 2}[tf]
    look = min(len(rows), {"1m": 375, "5m": 450, "15m": 400, "30m": 450, "1h": 450, "1D": 250, "1W": 260, "1M": 240}[tf])

    def lv(v):
        return round(v, 2) if v is not None else None

    ma_out = []
    for kind, m in mas:
        s = sma_series(closes, m) if kind == "SMA" else ema_full(closes, m)
        if any(v is not None for v in s):
            ma_out.append({"name": f"{kind} {m}", "values": [lv(v) for v in s]})
    bb_up, bb_lo = bollinger_series(closes)
    rsi = rsi_series(closes)
    ml, ms, mh = macd_series(closes)
    st_line, st_dir = supertrend(rows)
    lv_all = T.swing_levels(rows, price, window=window, lookback=look, tol=0.01 if tf in INTRADAY else 0.015)
    sup = sorted([l for l in lv_all if l["kind"] == "support"], key=lambda l: -l["level"])[:3]
    res = sorted([l for l in lv_all if l["kind"] == "resistance"], key=lambda l: l["level"])[:3]
    fib = T.fibonacci(rows, lookback=look)
    tls = T.trend_lines(rows, lookback=look, tol=0.008 if tf in INTRADAY else 0.012)
    pats = T.candle_patterns(rows, last=40)
    prev = rows[-2] if tf not in INTRADAY else None
    if tf in INTRADAY:  # pivots from the previous full day
        days_ = sorted({r["t"][:10] for r in rows})
        if len(days_) >= 2:
            pd_ = [r for r in rows if r["t"][:10] == days_[-2]]
            prev = {"high": max(r["high"] for r in pd_), "low": min(r["low"] for r in pd_), "close": pd_[-1]["close"], "date": days_[-2]}
    piv = T.pivots(prev) if prev else None
    out_rows = rows[-bars:] if bars else rows
    cut = len(rows) - len(out_rows)
    return {
        "tf": tf, "price": price, "last_time": rows[-1]["t"],
        "candles": [{"time": r["time"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"], "volume": r["volume"]} for r in out_rows],
        "mas": [{"name": m["name"], "values": m["values"][cut:]} for m in ma_out],
        "vwap": [lv(v) for v in vwap_series(rows)][cut:] if tf in INTRADAY else None,
        "bollinger": {"upper": [lv(v) for v in bb_up][cut:], "lower": [lv(v) for v in bb_lo][cut:]},
        "supertrend": {"values": [lv(v) for v in st_line][cut:], "direction": st_dir[cut:]},
        "rsi": [round(v, 1) if v is not None else None for v in rsi][cut:],
        "macd": {"line": [lv(v) for v in ml][cut:], "signal": [lv(v) for v in ms][cut:], "hist": [lv(v) for v in mh][cut:]},
        "supports": sup, "resistances": res, "fibonacci": fib,
        "trend_lines": [{**t, "from_time": rows[len(rows) - 1 - t["from"]["bars_ago"]]["time"], "last_time": rows[-1]["time"],
                         "value_from": t["from"]["price"],
                         "value_to": round(t["from"]["price"] + t["slope_per_day"] * t["from"]["bars_ago"], 2)} for t in tls],
        "patterns": [{**p, "time": rows[p["i"]]["time"]} for p in pats if p["i"] >= cut],
        "chart_patterns": T.chart_patterns(rows) if tf not in ("1m",) else [],
        "pivots": piv, "structure": market_structure(rows[-look:], window),
        "summary": {
            "rsi": round(rsi[-1], 1) if rsi[-1] is not None else None,
            "macd_above_signal": (ml[-1] > ms[-1]) if ml[-1] is not None and ms[-1] is not None else None,
            "supertrend": ("price above" if st_dir[-1] == 1 else "price below") if st_dir[-1] else None,
            "vs_mas": [{"name": m["name"], "value": m["values"][-1], "above": price > m["values"][-1]} for m in ma_out if m["values"][-1]],
            "vwap": lv(vwap_series(rows)[-1]) if tf in INTRADAY else None,
        },
    }


def multi_timeframe(key: str) -> list[dict]:
    """One row per timeframe: structure, position versus averages, RSI, Supertrend, nearest levels."""
    out = []
    for tf in ("1M", "1W", "1D", "1h", "30m", "15m", "5m", "1m"):
        try:
            c = chart(key, tf, bars=1)
        except Exception as e:  # one failing timeframe must not hide the others
            out.append({"tf": tf, "error": str(e)})
            continue
        if not c.get("candles"):
            out.append({"tf": tf, "error": c.get("error")})
            continue
        s = c["summary"]
        out.append({"tf": tf, "structure": c["structure"], "rsi": s["rsi"], "supertrend": s["supertrend"],
                    "macd_above_signal": s["macd_above_signal"], "vs_mas": s["vs_mas"], "vwap": s["vwap"],
                    "support": c["supports"][0]["level"] if c["supports"] else None,
                    "resistance": c["resistances"][0]["level"] if c["resistances"] else None, "price": c["price"]})
    return out
