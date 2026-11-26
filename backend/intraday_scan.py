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


def one(key: str, sym: str):
    try:
        c = charts.candles(key, "15m")
        d, _ = upstox_candles.daily(key, jobs.today_ist())
        a = intraday.analyse(c, d)
        bars15 = [[b["t"][:16], b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in c[-160:]]
        bars30 = [[b["t"][:16], b["open"], b["high"], b["low"], b["close"], b["volume"]] for b in intraday.to_30m(c)[-120:]]
        return key, sym, a, bars15, bars30
    except Exception as e:  # one stock failing must not stop the scan
        return key, sym, {"error": str(e)}, [], []


def main() -> None:
    init_db()  # a fresh machine has no local cache tables yet
    out = Path(sys.argv[1]) / "intraday"
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 1000
    uni = [(k, v["symbol"]) for k, v in derivatives.fno_universe().items() if k.startswith("NSE_EQ")][:mx]
    with ThreadPoolExecutor(3) as ex:
        res = list(ex.map(lambda kv: one(*kv), uni))
    setups, none, charts_ = [], [], {}
    for key, sym, a, b15, b30 in res:
        isin = key.split("|")[1]
        if "error" in a or not a.get("m15", {}).get("available"):
            continue
        charts_[isin] = {"symbol": sym, "a": a, "b15": b15, "b30": b30}
        found = False
        for tf in ("m15", "m30"):
            s = a[tf].get("setup")
            if s:
                found = True
                other = a["m30" if tf == "m15" else "m15"]
                both = (other.get("setup") or {}).get("direction") == s["direction"]
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
                setups.append({"isin": isin, "symbol": sym, "tf": a[tf]["tf"], "as_of": a[tf]["as_of"], "price": px, "status": status,
                               **{k: s[k] for k in ("direction", "type", "entry_zone", "stop", "targets", "reward_risk", "reasons", "agree", "of")},
                               "both_timeframes": both, "daily_trend": a["daily_trend"], "caution": a[tf]["caution"]})
        if not found:
            none.append({"isin": isin, "symbol": sym, "price": a.get("live_price"), "wait": a["m15"]["verdict"], "trend15": a["m15"]["trend"], "trend30": a["m30"].get("trend")})
    setups.sort(key=lambda s: (not s["both_timeframes"], -s["agree"], -(s["reward_risk"] or 0)))
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    n = max(1, len(charts_) // 15 + 1)
    groups = {}
    for i, c in charts_.items():
        groups.setdefault(bucket(i, n), {})[i] = c
    for k in range(n):
        (out / f"c{k:02d}.json").write_text(json.dumps({"z": z(groups.get(k, {}))}))
    now = datetime.now(IST)
    live = {"generated_at": now.isoformat(timespec="seconds"), "chunks": n, "scanned": len(charts_), "setups": setups, "no_entry": none,
            "method": "Every F&O stock, on closed 15-min and 30-min candles. Breakout: a candle closing beyond a key level (previous day high/low, VWAP, pivots, swing levels, pattern lines) on 1.5× volume with ADX ≥ 20 and RSI in the trend's range. Pullback: an intraday trend (20 EMA vs 50 EMA, VWAP, Dow structure) with price back at the 20 EMA, VWAP or support and a candle turning with the trend. Entry zone, stop where the setup is wrong, targets at the next levels; shown only when reward:risk ≥ 1.5. Confirmations: daily trend, Supertrend, MACD.",
            "note": "Chart analysis for you to decide on; no trades are placed and no position sizes are given."}
    (out / "live.json").write_text(json.dumps({"z": z(live), "generated_at": live["generated_at"], "chunks": n}))
    print(f"scanned {len(charts_)} of {len(uni)}; {len(setups)} setups; {n} chart documents")


if __name__ == "__main__":
    main()
