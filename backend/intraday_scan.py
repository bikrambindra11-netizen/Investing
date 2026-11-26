"""15/30-minute scan of every F&O stock (the liquid ones day traders use): map each chart, test for entry
points, and write page-database documents.

Usage: python -m backend.intraday_scan OUT_DIR [--max N]
Writes OUT_DIR/intraday/live.json (every setup found, ranked, plus the no-entry list) and OUT_DIR/intraday/cNN.json
(per-stock charts: last 15-min and 30-min candles with levels and the setup), gzip + base64."""
import base64
import gzip
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import charts, derivatives, intraday, jobs  # noqa: E402
from backend.app.db import init_db  # noqa: E402
from backend.build_cards import bucket  # noqa: E402
from backend.sources import upstox_candles  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")


def z(o) -> str:
    return base64.b64encode(gzip.compress(json.dumps(o, separators=(",", ":"), default=str).encode(), 9)).decode()


KEEP = {"m1": 240, "m5": 200, "m15": 160, "m30": 120, "h1": 100, "d1": 260, "w1": 156, "mo1": 120}


def pack(rows, n):
    return [[b["t"][:16].replace("T", " "), round(b["open"], 2), round(b["high"], 2), round(b["low"], 2), round(b["close"], 2), b["volume"]] for b in rows[-n:]]


def one(key: str, sym: str):
    try:
        c1, c5, c15 = charts.candles(key, "1m"), charts.candles(key, "5m"), charts.candles(key, "15m")
        d, _ = upstox_candles.daily(key, jobs.today_ist())
        # today's daily bar from the intraday candles (the daily history ends yesterday)
        today = jobs.today_ist().isoformat()
        tod = [b for b in c15 if b["t"][:10] == today]
        if tod and (not d or d[-1]["date"] < today):
            d = d + [{"date": today, "open": tod[0]["open"], "high": max(b["high"] for b in tod), "low": min(b["low"] for b in tod),
                      "close": (c1 or tod)[-1]["close"], "volume": sum(b["volume"] for b in tod)}]
        a = intraday.analyse_all(c1, c5, c15, d)
        dbars = [{"t": x["date"] + "T09:15:00+05:30", **x} for x in d]
        bars = {"m1": pack(c1, KEEP["m1"]), "m5": pack(c5, KEEP["m5"]), "m15": pack(c15, KEEP["m15"]), "m30": pack(intraday.to_30m(c15), KEEP["m30"]),
                "h1": pack(intraday.to_60m(c15), KEEP["h1"]), "d1": pack(dbars, KEEP["d1"]), "w1": pack(intraday.to_period(dbars, "W"), KEEP["w1"]),
                "mo1": pack(intraday.to_period(dbars, "M"), KEEP["mo1"])}
        return key, sym, a, bars
    except Exception as e:  # one stock failing must not stop the scan
        return key, sym, {"error": str(e)}, {}


def main() -> None:
    init_db()  # a fresh machine has no local cache tables yet
    out = Path(sys.argv[1]) / "intraday"
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 1000
    uni = [(k, v["symbol"]) for k, v in derivatives.fno_universe().items() if k.startswith("NSE_EQ")][:mx]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda kv: one(*kv), uni))
    setups, none, charts_, forming = [], [], {}, []
    for key, sym, a, bars in res:
        isin = key.split("|")[1]
        if "error" in a or not a.get("m15", {}).get("available"):
            continue
        charts_[isin] = {"symbol": sym, "a": a, "bars": bars}
        found = False
        for tf, _label in intraday.TF_ORDER:
            s = (a.get(tf) or {}).get("setup")
            if s:
                found = True
                same = [l for t, l in intraday.TF_ORDER if t != tf and ((a.get(t) or {}).get("setup") or {}).get("direction") == s["direction"]]
                trend_agree = [l for t, l in intraday.TF_ORDER if t != tf and (a.get(t) or {}).get("trend") == ("up" if s["direction"] == "long" else "down")]
                both = bool(same)
                px, atr = a.get("live_price"), (a[tf]["ind"] or {}).get("atr") or 0
                lo, hi = s["entry_zone"]
                if px is None:
                    status = "—"
                elif lo - 0.25 * atr <= px <= hi + 0.25 * atr:
                    status = "price is in the entry zone now"
                elif (s["direction"] == "long" and px > hi) or (s["direction"] == "short" and px < lo):
                    status = "price has already moved past the entry zone: chasing is worse reward:risk; wait for a retest of the zone"
                else:
                    status = "price has moved against the setup, toward the stop"
                if px is not None and ((s["direction"] == "long" and px <= s["stop"]) or (s["direction"] == "short" and px >= s["stop"])):
                    status = "stop level already broken: setup failed"
                setups.append({"isin": isin, "symbol": sym, "tf": a[tf]["tf"], "tf_key": tf, "as_of": a[tf]["as_of"], "price": px, "status": status,
                               "entry": s.get("entry"), "tf_passed": s.get("tf_passed"), "tf_checks": s.get("tf_checks"),
                               "other_setups": same, "trend_agrees_on": trend_agree,
                               **{k: s[k] for k in ("direction", "type", "entry_zone", "stop", "targets", "reward_risk", "reasons", "agree", "of")},
                               "both_timeframes": both, "daily_trend": a["daily_trend"], "caution": a[tf]["caution"]})
        for tf, _label in intraday.TF_ORDER:
            f = (a.get(tf) or {}).get("forming")
            if f:
                forming.append({"isin": isin, "symbol": sym, "tf": a[tf]["tf"], "tf_key": tf, "price": a.get("live_price"),
                                **{k: f[k] for k in ("direction", "type", "entry_zone", "stop", "targets", "reward_risk", "reasons", "agree", "of",
                                                     "closes_at", "minutes_left", "tf_passed", "tf_checks", "entry_if_closes")}})
        if not found:
            none.append({"isin": isin, "symbol": sym, "price": a.get("live_price"), "wait": a["m15"]["verdict"],
                         "trends": {l: (a.get(t) or {}).get("trend") for t, l in intraday.TF_ORDER}})
    setups.sort(key=lambda s: (not s["entry"], -(s["tf_passed"] or 0), -s["agree"], -(s["reward_risk"] or 0)))
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    n = 120  # fixed, so quick runs that only rewrite the list stay consistent with the chart documents
    while True:  # every document under the database's 256 KiB limit
        groups = {}
        for i, c in charts_.items():
            groups.setdefault(bucket(i, n), {})[i] = c
        blobs = {k: json.dumps({"z": z(groups.get(k, {}))}) for k in range(n)}
        if max(len(b) for b in blobs.values()) <= 240_000:
            break
        n += max(1, n // 8)
    for k, b in blobs.items():
        (out / f"c{k:02d}.json").write_text(b)
    now = datetime.now(IST)
    forming.sort(key=lambda f: (not f["entry_if_closes"], -f["tf_passed"], f["minutes_left"]))
    live = {"generated_at": now.isoformat(timespec="seconds"), "chunks": n, "scanned": len(charts_), "setups": setups, "no_entry": none, "forming": forming,
            "method": "Every F&O stock on every timeframe (1-min, 5-min, 15-min, 30-min, 1-hour, daily, weekly, monthly), on closed candles. Breakout: a candle closing beyond a key level (previous day high/low, VWAP, pivots, swing levels, pattern lines) on 1.5× volume with ADX ≥ 20 and RSI in the trend's range. Pullback: an intraday trend (20 EMA vs 50 EMA, VWAP, Dow structure) with price back at the 20 EMA, VWAP or support and a candle turning with the trend. Entry zone, stop where the setup is wrong, targets at the next levels; shown only when reward:risk ≥ 1.5. Confirmations: daily trend, Supertrend, MACD.",
            "note": "Chart analysis for you to decide on; no trades are placed and no position sizes are given."}
    (out / "live.json").write_text(json.dumps({"z": z(live), "generated_at": live["generated_at"], "chunks": n}))
    files = sorted(out.glob("c*.json")) + [out / "live.json"]
    batches, cur, size = [], [], 0
    for f in files:
        sz = f.stat().st_size
        if cur and (size + sz > 900_000 or len(cur) >= 40 or f.name == "live.json"):
            batches.append(cur)
            cur, size = [], 0
        cur.append(f.name[:-5])
        size += sz
    batches.append(cur)
    (out.parent / "batches.json").write_text(json.dumps(batches))
    print(f"scanned {len(charts_)} of {len(uni)}; {len(setups)} setups; {n} chart documents; {len(batches)} write batches (see batches.json)")


if __name__ == "__main__":
    main()
