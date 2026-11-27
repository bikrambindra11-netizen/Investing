"""Backtest of the trading rules: replay the exact live setup rules (backend/app/intraday.py) candle by candle on
past data for every F&O stock, take each signal the way the panel shows it, and record what happened.

Usage: python -m backend.backtest OUT.json [--days 120] [--max N]

Rules simulated exactly as shown on the panel:
  - signal on a CLOSED candle (15-min, 30-min, 1-hour; daily separately on 10 years of history)
  - the timeframe trends must agree: 15-min, 30-min, 1-hour, daily, weekly, monthly (1-min and 5-min have too
    little history to test, so the live 8-timeframe rule is checked here on 6)
  - entry only if price trades into the entry zone within the next 4 candles; filled at the middle of the zone
  - exit at the stop or target 1, whichever is hit first (if both in the same candle: stop, the worse case);
    intraday trades are closed at the last candle of the day; daily trades after 10 sessions
  - costs: 0.05% of price per round trip (brokerage, STT, slippage), taken off every trade
Result per rule (timeframe x setup type x direction), pooled across all stocks and per stock: trades, win rate,
average win and loss in R (multiples of the risk), expectancy in R per trade."""
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import charts, derivatives, intraday, jobs  # noqa: E402
from backend.app.db import init_db  # noqa: E402
from backend.sources import upstox_candles  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
COST = 0.0005
FILL_WITHIN = 4


def history_15m(key: str, days: int) -> list[dict]:
    """15-minute candles for the last `days` days (the API serves at most a month per request) plus today."""
    k = quote(key, safe="")
    today = datetime.now(IST).date()
    rows = {}
    end = today
    while (today - end).days < days:
        start = end - timedelta(days=28)
        for r in charts._get(f"{charts.BASE}/{k}/minutes/15/{end.isoformat()}/{start.isoformat()}"):
            rows[r[0]] = r
        end = start - timedelta(days=1)
    for r in charts._get(f"{charts.BASE}/intraday/{k}/minutes/15"):
        rows[r[0]] = r
    return charts._to_rows(list(rows.values()))


def trend_series(c: list[dict], htf: bool) -> list[str]:
    """Trend on each closed bar, the same definition as the live panel (20 vs 50 EMA, price vs VWAP or 20 EMA)."""
    out, e20, e50 = [], None, None
    k20, k50 = 2 / 21, 2 / 51
    day, pv, vv = None, 0.0, 0.0
    for b in c:
        e20 = b["close"] if e20 is None else b["close"] * k20 + e20 * (1 - k20)
        e50 = b["close"] if e50 is None else b["close"] * k50 + e50 * (1 - k50)
        if not htf:
            d = b["t"][:10]
            if d != day:
                day, pv, vv = d, 0.0, 0.0
            pv += (b["high"] + b["low"] + b["close"]) / 3 * b["volume"]
            vv += b["volume"]
            ref = pv / vv if vv else e20
        else:
            ref = e20
        out.append("up" if e20 > e50 and b["close"] > ref else "down" if e20 < e50 and b["close"] < ref else "sideways")
    return out


def _end_ts(b: dict, minutes: int | None) -> float:
    t = datetime.fromisoformat(b["t"])
    if minutes is None:  # daily bar closes at 15:30
        return t.replace(hour=15, minute=30).timestamp()
    return t.timestamp() + minutes * 60


def simulate(series: list[dict], i: int, s: dict, intraday_tf: bool, max_bars: int) -> dict | None:
    """Fill within FILL_WITHIN bars, then stop or target 1; intraday trades closed at the day's last bar."""
    lo, hi = s["entry_zone"]
    long = s["direction"] == "long"
    entry = (lo + hi) / 2
    risk = abs(entry - s["stop"])
    if not risk:
        return None
    day = series[i]["t"][:10]
    filled = None
    for j in range(i + 1, min(i + 1 + FILL_WITHIN, len(series))):
        b = series[j]
        if intraday_tf and b["t"][:10] != day:
            return None  # no fill the same day
        if b["low"] <= hi and b["high"] >= lo:
            filled = j
            break
    if filled is None:
        return None
    exit_px, how = None, None
    for j in range(filled, min(filled + max_bars, len(series))):
        b = series[j]
        if intraday_tf and b["t"][:10] != series[filled]["t"][:10]:
            prev = series[j - 1]
            exit_px, how = prev["close"], "day end"
            break
        stop_hit = b["low"] <= s["stop"] if long else b["high"] >= s["stop"]
        tgt_hit = b["high"] >= s["targets"][0] if long else b["low"] <= s["targets"][0]
        if j == filled:  # the fill candle: only count the stop if price went through it after filling (conservative: count it)
            pass
        if stop_hit:
            exit_px, how = s["stop"], "stop"
            break
        if tgt_hit:
            exit_px, how = s["targets"][0], "target"
            break
    if exit_px is None:
        last = series[min(filled + max_bars, len(series)) - 1]
        exit_px, how = last["close"], "time"
    pnl = (exit_px - entry) if long else (entry - exit_px)
    r = (pnl - COST * entry) / risk
    return {"r": round(r, 3), "how": how, "entry": round(entry, 2), "time": series[i]["t"][:16]}


def run_stock(arg):
    key, sym, days = arg
    try:
        init_db()
        c15 = history_15m(key, days)
        daily, _ = upstox_candles.daily(key, jobs.today_ist())
    except Exception as e:  # noqa: BLE001
        return sym, {"error": str(e)}, []
    if len(c15) < 300 or len(daily) < 300:
        return sym, {"error": "not enough history"}, []
    now = datetime.now(IST)
    c15 = [b for b in c15 if datetime.fromisoformat(b["t"]).timestamp() + 900 <= now.timestamp()]
    tfs = {"15-min": (c15, 15), "30-min": (intraday.to_30m(c15), 30), "1-hour": (intraday.to_60m(c15), 60)}
    dbars = [{"t": d["date"][:10] + "T09:15:00+05:30", **d} for d in daily]
    wk, mo = intraday.to_period(dbars, "W"), intraday.to_period(dbars, "M")
    # trend timelines: (bar end time, trend) for each timeframe
    tl = {}
    for name, (c, m) in tfs.items():
        tl[name] = list(zip([_end_ts(b, m) for b in c], trend_series(c, False)))
    tl["daily"] = list(zip([_end_ts(b, None) for b in dbars], trend_series(dbars, True)))
    # weekly/monthly bars close at the end of their last session
    def period_end(bars, kind):
        out = []
        for n, b in enumerate(bars):
            nxt = bars[n + 1]["t"] if n + 1 < len(bars) else None
            end = (datetime.fromisoformat(nxt) - timedelta(hours=18)).replace(hour=15, minute=30) if nxt else datetime.max.replace(tzinfo=IST)
            out.append(end.timestamp() if nxt else 9e12)
        return out
    tl["weekly"] = list(zip(period_end(wk, "W"), trend_series(wk, True)))
    tl["monthly"] = list(zip(period_end(mo, "M"), trend_series(mo, True)))

    def trend_at(name, ts):
        arr = tl[name]
        lo_, hi_ = 0, len(arr) - 1
        ans = None
        while lo_ <= hi_:
            mid = (lo_ + hi_) // 2
            if arr[mid][0] <= ts:
                ans = arr[mid][1]
                lo_ = mid + 1
            else:
                hi_ = mid - 1
        return ans

    trades = []
    names = ["15-min", "30-min", "1-hour", "daily", "weekly", "monthly"]
    for name, (c, m) in tfs.items():
        for i in range(120, len(c) - 1):
            a = intraday.analyse_tf(c[max(0, i - 400):i + 1], name, None)
            if not a.get("available"):
                continue
            for s in a.get("setups") or []:
                if not s.get("valid"):
                    continue
                ts = _end_ts(c[i], m)
                want = "up" if s["direction"] == "long" else "down"
                others = [trend_at(n, ts) for n in names if n != name]
                agree = sum(t == want for t in others)
                res = simulate(c, i, s, True, 40)
                if res:
                    trades.append({"sym": sym, "tf": name, "type": s["type"], "dir": s["direction"], "agree": agree, "of": len(others), **res})
    # daily setups over the last 3 years (weekly/monthly alignment only: no intraday history that far back)
    for i in range(max(260, len(dbars) - 750), len(dbars) - 1):
        a = intraday.analyse_tf(dbars[max(0, i - 400):i + 1], "daily", None, htf=True)
        for s in a.get("setups") or []:
            if not s.get("valid"):
                continue
            ts = _end_ts(dbars[i], None)
            want = "up" if s["direction"] == "long" else "down"
            others = [trend_at(n, ts) for n in ("weekly", "monthly")]
            res = simulate(dbars, i, s, False, 10)
            if res:
                trades.append({"sym": sym, "tf": "daily", "type": s["type"], "dir": s["direction"], "agree": sum(t == want for t in others), "of": 2, **res})
    return sym, {"bars15": len(c15)}, trades


def summarise(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    rs = [t["r"] for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    return {"trades": len(rs), "win_rate_pct": round(len(wins) / len(rs) * 100, 1),
            "avg_win_r": round(sum(wins) / len(wins), 2) if wins else None, "avg_loss_r": round(sum(losses) / len(losses), 2) if losses else None,
            "expectancy_r": round(sum(rs) / len(rs), 3), "total_r": round(sum(rs), 1),
            "profit_factor": round(sum(wins) / -sum(losses), 2) if losses and sum(losses) < 0 else None}


def main() -> None:
    out = sys.argv[1]
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 120
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 1000
    init_db()
    uni = [(k, v["symbol"], days) for k, v in derivatives.fno_universe().items() if k.startswith("NSE_EQ")][:mx]
    t0 = time.time()
    # fetch in threads (network), compute in processes
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(lambda a: upstox_candles.daily(a[0], jobs.today_ist()), uni))  # warm the daily cache
    all_trades, errors = [], {}
    with ProcessPoolExecutor(4) as ex:
        for n, (sym, info, trades) in enumerate(ex.map(run_stock, uni), 1):
            if "error" in info:
                errors[sym] = info["error"]
            all_trades += trades
            if n % 20 == 0:
                print(f"{n}/{len(uni)} stocks, {len(all_trades)} trades, {time.time() - t0:.0f}s", flush=True)
    groups = defaultdict(list)
    for t in all_trades:
        aligned = "all agree" if t["agree"] == t["of"] else "not all agree"
        groups[(t["tf"], t["type"], t["dir"], aligned)].append(t)
        groups[(t["tf"], t["type"], t["dir"], "any")].append(t)
    pooled = [{"tf": k[0], "type": k[1], "direction": k[2], "alignment": k[3], **summarise(v)} for k, v in sorted(groups.items())]
    per_stock = defaultdict(list)
    for t in all_trades:
        if t["agree"] == t["of"]:
            per_stock[(t["sym"], t["tf"], t["type"], t["dir"])].append(t)
    stock_rows = [{"symbol": k[0], "tf": k[1], "type": k[2], "direction": k[3], **summarise(v)} for k, v in per_stock.items()]
    res = {"generated_at": datetime.now(IST).isoformat(timespec="seconds"), "days": days, "stocks": len(uni), "errors": errors,
           "pooled": pooled, "per_stock": stock_rows, "trades": all_trades,
           "method": __doc__}
    with open(out, "w") as fh:
        json.dump(res, fh, default=str)
    print(f"done: {len(all_trades)} trades from {len(uni) - len(errors)} stocks in {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
