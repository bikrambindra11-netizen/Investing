"""Build the hosted web page (OUT_DIR/index.html) with all its data embedded.

Usage: python -m backend.export_snapshot OUT_DIR [--charts N] [--news N]
Run after the data jobs have refreshed the database.
"""
import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from backend.app import analysis, macro, technicals
from backend.app.db import SessionLocal
from backend.app.jobs import today_ist
from backend.app.market_data import INDEX_TILES, build_rows
from backend.app.stock import company_news, industry_news
from backend.sources import nse_sectors, upstox_candles


TEMPLATE = Path(__file__).resolve().parents[1] / "site" / "template.html"


def slug(industry_id: str) -> str:
    return industry_id.replace("_", "-")


def candles_for(key: str) -> list[dict]:
    try:
        return upstox_candles.daily(key, today_ist())[0]
    except Exception:
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--charts", type=int, default=800, help="price history for the N most traded stocks")
    ap.add_argument("--news", type=int, default=250, help="news for the N most traded stocks")
    ap.add_argument("--tech", type=int, default=450, help="candles + chart structure for the N most traded stocks")
    ap.add_argument("--live", type=int, default=1000, help="today's latest price for the N most traded stocks")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as s:
        rows, as_of = build_rows(s)
    rows.sort(key=lambda r: -(r["turnover"] or 0))

    # Latest traded prices today (1-minute candles) for indices and the most traded stocks
    with ThreadPoolExecutor(8) as ex:
        live_keys = [k for _, _, k in INDEX_TILES] + [r["key"] for r in rows[: a.live]]
        trades = dict(zip(live_keys, ex.map(upstox_candles.last_trade, live_keys)))

    # Index tiles from Upstox daily candles (covers Sensex too)
    indices = []
    for label, _, key in INDEX_TILES:
        c = candles_for(key)
        if len(c) >= 2:
            close, prev, when = c[-1]["close"], c[-2]["close"], c[-1]["date"]
            t = trades.get(key)
            if t and t["time"][:10] > when:  # today's session is newer than the last daily candle
                close, prev, when = t["price"], c[-1]["close"], t["time"]
            elif t and t["time"][:10] == when:
                close, when = t["price"], t["time"]
            indices.append({"label": label, "close": close, "prev": prev, "date": when,
                            "change_pct": round((close / prev - 1) * 100, 2),
                            "trend": [[x["date"], x["close"]] for x in c[-260:]]})
        else:
            indices.append({"label": label, "close": None})

    # Price history + stats for the most traded stocks
    top = [r for r in rows if r["close"] is not None][: a.charts]
    with ThreadPoolExecutor(6) as ex:
        hist = dict(zip([r["isin"] for r in top], ex.map(lambda r: candles_for(r["key"]), top)))
    charts, stats = {}, {}
    by_isin = {r["isin"]: r for r in top}
    for isin, c in hist.items():
        if not c:
            continue
        r = by_isin[isin]
        if r["price_date"] and r["close"] and r["price_date"] > c[-1]["date"]:
            # The exchange close file is newer than Upstox's daily history: add that close.
            c = c + [{"date": r["price_date"], "open": r["close"], "high": r["close"], "low": r["close"],
                      "close": r["close"], "volume": r["volume"] or 0}]
        stats[isin] = analysis.price_stats(c)
        last5 = [x for x in c if x["date"] >= str(int(c[-1]["date"][:4]) - 5) + c[-1]["date"][4:]]
        daily = last5[-260:]
        weekly = last5[:-260][::5]
        charts[isin] = [[x["date"].replace("-", ""), x["close"]] for x in weekly + daily]

    # News for the most traded stocks and every industry
    news = {}
    with ThreadPoolExecutor(4) as ex:
        for r, n in zip(rows[: a.news], ex.map(lambda r: company_news(r["name"] or r["symbol"]), rows[: a.news])):
            news[r["isin"]] = n["items"][:8]
    inds = macro.load_industries()
    industries = {}
    for iid in inds:
        m = macro.industry_macro(iid)
        industries[slug(iid)] = {**m, "id": slug(iid), "news": industry_news(inds[iid]["label"])["items"][:10]}

    stocks = []
    for r in rows:
        t = trades.get(r["key"])
        live = None
        if t and r["price_date"] and t["time"][:10] > r["price_date"] and r["close"]:
            # Trading today, and the exchange close file is from an earlier day
            live = {"lp": t["price"], "lch": round((t["price"] / r["close"] - 1) * 100, 2), "lt": t["time"]}
        stocks.append({
            **(live or {}),
            "i": r["isin"], "s": r["symbol"], "n": (r["name"] or "").title(), "x": r["exchanges"],
            "c": r["close"], "p": r["prev_close"], "ch": r["change_pct"], "v": r["volume"], "t": r["turnover"],
            "d": r["price_date"], "src": r["price_source"], "sec": r.get("sector"),
            "ms": nse_sectors.SECTOR_TO_MACRO.get(r.get("sector")) if r.get("sector") else None,
            "ind": slug(r["industry"]),
        })

    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prices_as_of": as_of,
            "counts": {"stocks": len(stocks), "charts": len(charts), "news": len(news)}}
    # Candles + chart structure for the most traded stocks, so a stock page opens with the
    # candlestick chart, patterns and levels already marked.
    tech, cal = {}, []
    nifty = candles_for("NSE_INDEX|Nifty 50")
    cal = [x["date"] for x in nifty[-90:]]
    meanings = {}
    for isin, c in list(hist.items())[: a.tech]:
        if len(c) < 60:
            continue
        t = technicals.analyse(c, c[-1]["close"])
        st = technicals.structure(c)
        by_date = {x["date"]: x for x in c}
        if c[-1]["date"] not in cal and c[-1]["date"] > (cal[-1] if cal else ""):
            cal.append(c[-1]["date"])
        bars = [by_date.get(d) for d in cal]
        for p in st["candles"]:
            if not p["pattern"].startswith("Gap"):
                meanings[p["pattern"]] = p["meaning"]
        meanings["Gap up"] = "opened above the previous day's high, leaving a price gap"
        meanings["Gap down"] = "opened below the previous day's low, leaving a price gap"
        tech[isin] = {
            "bars": [[round(x["open"], 2), round(x["high"], 2), round(x["low"], 2), round(x["close"], 2), x["volume"]] if x else None for x in bars],
            "supports": [{"level": l["level"], "touches": l["touches"], "distance_pct": l["distance_pct"]} for l in t["supports"]],
            "resistances": [{"level": l["level"], "touches": l["touches"], "distance_pct": l["distance_pct"]} for l in t["resistances"]],
            "ma": t["moving_averages"], "rsi": t["rsi14"], "atr_pct": t["atr_pct"], "volume_ratio": t["volume_ratio"],
            "pivots": t["pivots"], "observations": t["observations"],
            "fib": st["fibonacci"], "trend_lines": st["trend_lines"], "patterns": [[p["date"], p["pattern"], p["price"]] for p in st["candles"] if p["date"] >= cal[0]],
            "chart_patterns": st["chart_patterns"], "weekly": st["weekly"]["structure"],
        }

    # Charts on one shared date axis (weekly for older years, daily for the last year) to keep the page small.
    dates = sorted({d for v in charts.values() for d, _ in v})
    cutoff = dates[-1][:4] and str(int(dates[-1][:4]) - 1) + dates[-1][4:] if dates else ""
    axis = [d for i, d in enumerate(dates) if d >= cutoff or i % 5 == 0]
    series = {}
    for isin, pts in charts.items():
        m, last, row = dict(pts), None, []
        for d in axis:
            if d in m:
                last = m[d]
            row.append(last)
        series[isin] = row

    data = {"stocks": stocks, "indices": indices, "industries": industries, "economy": macro.all_indicators(),
            "stats": stats, "news": {k: v[:5] for k, v in news.items()}, "meta": meta,
            "charts": {"dates": axis, "series": series},
            "tech": {"calendar": cal, "meanings": meanings, "stocks": tech}}
    blob = json.dumps(data, separators=(",", ":"), default=str).replace("<", "\\u003c")
    page = TEMPLATE.read_text().replace("__PORTAL_DATA__", blob)
    (out / "index.html").write_text(page)
    print(f"index.html: {(out / 'index.html').stat().st_size / 1e6:.2f} MB with data embedded")


if __name__ == "__main__":
    main()
