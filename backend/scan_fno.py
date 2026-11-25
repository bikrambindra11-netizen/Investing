"""Market pulse for stocks with futures & options: where something unusual is happening right now.

Usage: python -m backend.scan_fno OUT.json
For each F&O stock: today's move, volume versus normal, open-interest build-up, implied volatility,
and where price sits against its key levels and 52-week range. It ranks by how unusual the activity
is (not by any buy/sell signal) and attaches recent headlines to the most notable names, so the
whole picture can be read together.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

os.environ.setdefault("RUN_JOBS", "false")
os.environ.setdefault("UPSTOX_ACCESS_TOKEN", "proxy-injected")

from backend.app import derivatives, jobs, technicals  # noqa: E402
from backend.app.db import init_db  # noqa: E402
from backend.app.stock import company_news  # noqa: E402
from backend.sources import upstox_bulk, upstox_candles  # noqa: E402


def main() -> None:
    out_path = sys.argv[1]
    init_db()
    today = jobs.today_ist()
    uni = derivatives.fno_universe()
    keys = list(uni)
    prices = upstox_bulk.last_prices(keys)

    def one(k):
        u = uni[k]
        try:
            c = upstox_candles._fetch(k, today, None)
        except Exception:
            return None
        if len(c) < 60:
            return None
        price = prices.get(k) or c[-1]["close"]
        prev = c[-1]["close"] if c[-1]["date"] < today.isoformat() else c[-2]["close"]
        t = technicals.analyse(c, price)
        exp = derivatives.pick_expiry(u["expiries"], today, min_days=3)
        chain = derivatives.read_chain(derivatives.option_chain(k, exp)) if exp and u["has_options"] else {"available": False}
        change = round((price / prev - 1) * 100, 2) if prev else None
        flags, weight = [], 0.0
        if change is not None and abs(change) >= max(2.0, 1.5 * (t.get("atr_pct") or 0)):
            flags.append(f"Moved {change:+.1f}% — larger than its normal daily move ({t.get('atr_pct')}%).")
            weight += min(abs(change) / max(t.get("atr_pct") or 1, 0.5), 4)
        if t.get("volume_ratio") and t["volume_ratio"] >= 2:
            flags.append(f"Volume {t['volume_ratio']}× normal.")
            weight += min(t["volume_ratio"] / 2, 4)
        if chain.get("available"):
            tot = sum((r["ce"].get("prev_oi") or 0) + (r["pe"].get("prev_oi") or 0) for r in chain["rows"]) or 1
            doi = (chain["call_oi_change"] + chain["put_oi_change"]) / tot * 100
            if abs(doi) >= 15 and tot >= 200 * u["lot_size"]:  # ignore build-ups from a tiny base
                flags.append(f"Option open interest {'up' if doi > 0 else 'down'} {abs(doi):.0f}% in a day "
                             f"(calls {chain['call_oi_change']:+,.0f}, puts {chain['put_oi_change']:+,.0f}).")
                weight += min(abs(doi) / 15, 3)
            if chain.get("atm_iv") and chain["atm_iv"] >= 45:
                flags.append(f"Implied volatility high at {chain['atm_iv']}%: the options market expects big moves.")
                weight += chain["atm_iv"] / 45 - 0.5
        if t.get("available"):
            if price >= t["high_52w"] * 0.99:
                flags.append("At or near its 52-week high.")
                weight += 1
            elif price <= t["low_52w"] * 1.01:
                flags.append("At or near its 52-week low.")
                weight += 1
            if t["resistances"] and prev < t["resistances"][0]["level"] <= price:
                flags.append(f"Crossed resistance at ₹{t['resistances'][0]['level']:,.2f} today.")
                weight += 1
            if t["supports"] and prev > t["supports"][0]["level"] >= price:
                flags.append(f"Fell through support at ₹{t['supports'][0]['level']:,.2f} today.")
                weight += 1
        pos = derivatives.positioning(u["symbol"], u["lot_size"], t, chain, today)
        return {"symbol": u["symbol"], "isin": k.split("|")[-1], "price": price, "change_pct": change,
                "notable": round(weight, 2), "flags": flags, "volume_ratio": t.get("volume_ratio"), "rsi": t.get("rsi14"),
                "atr_pct": t.get("atr_pct"), "iv": chain.get("atm_iv"), "pcr": chain.get("pcr"),
                "expected_move_pct": (pos.get("expected_move") or {}).get("pct"), "positioning": pos}

    with ThreadPoolExecutor(6) as ex:
        rows = [r for r in ex.map(one, keys) if r]
    rows.sort(key=lambda r: -r["notable"])
    notable = [r for r in rows if r["flags"]][:25]
    with ThreadPoolExecutor(4) as ex:
        for r, n in zip(notable, ex.map(lambda r: company_news(r["symbol"])["items"][:3], notable)):
            r["headlines"] = [{"title": x["title"], "link": x["link"], "publisher": x["publisher"]} for x in n]
    breadth = {"up": sum(1 for r in rows if (r["change_pct"] or 0) > 0), "down": sum(1 for r in rows if (r["change_pct"] or 0) < 0)}
    result = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "universe": len(keys),
              "scanned": len(rows), "breadth": breadth, "notable": notable,
              "overview": [{k: r[k] for k in ("symbol", "isin", "price", "change_pct", "volume_ratio", "iv", "pcr", "expected_move_pct")} for r in rows],
              "label": "Where unusual activity is happening, with facts and news. Not recommendations; read it with the full analysis of each stock."}
    with open(out_path, "w") as fh:
        json.dump(result, fh, default=str)
    with open(out_path + ".db.json", "w") as fh:  # fields for the page's scans/latest document
        json.dump({"status": "working", "step": "Data collected. Claude is reading the news and writing the market overview…",
                   "updated_at": result["generated_at"], "scan": result}, fh, default=str)
    print(f"wrote {out_path}: {len(rows)} stocks, {len(notable)} with unusual activity, {os.path.getsize(out_path) // 1024} KB")


if __name__ == "__main__":
    main()
