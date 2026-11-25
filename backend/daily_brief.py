"""Today's brief: the day's market-moving news priced into industries and companies, combined with each
company's fundamentals (precomputed cards) and the important technical indicators, into three screens:

  investing  - strongest fundamentals, adjusted for today's news, with the technical picture as context
  trading    - strongest technical structure among companies whose fundamentals are not weak and whose
               news is not against them
  caution    - well-known names where today's news or the chart has turned against them

Usage: python -m backend.daily_brief EVENTS.json CARDS_DIR OUT.json [--refresh]
EVENTS.json is written each day by the analyst (Claude) from the news: summary, events with industry
impacts in -2..+2 and sources, and company-specific items. Screening output, not advice."""
import base64
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("RUN_JOBS", "false")

from backend.app import indicators, jobs, patterns  # noqa: E402
from backend.app.db import DailyPrice, SessionLocal, init_db  # noqa: E402
from backend.app.market_data import build_rows  # noqa: E402
from backend.sources import cache, upstox_candles  # noqa: E402
from datetime import timedelta  # noqa: E402

W_FUND, W_TECH, W_NEWS = 0.45, 0.35, 0.20


def load_cards(d: Path) -> dict:
    out = {}
    for f in sorted(d.glob("c*.json")):
        doc = json.loads(f.read_text())
        doc = doc.get("data", doc) if "z" not in doc else doc  # local build file, or a document saved by ArtifactData
        out.update(json.loads(gzip.decompress(base64.b64decode(doc["z"]))))
    return out


def candles(key: str, row: dict, fetch: bool = False) -> list[dict]:
    hit = cache.get(f"candles:{key}", timedelta(days=3))
    if not hit and fetch:
        try:
            hit = upstox_candles.daily(key, jobs.today_ist())
        except Exception:
            hit = None
    if not hit:
        return []
    c = list(hit[0])
    if c and row.get("price_date") and row["price_date"] > c[-1]["date"] and row.get("close"):
        c.append({"date": row["price_date"], "open": row.get("open") or row["close"], "high": row.get("high") or row["close"],
                  "low": row.get("low") or row["close"], "close": row["close"], "volume": row.get("volume") or 0})
    return c


def main() -> None:
    ev_path, cards_dir, out_path = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    ev = json.loads(Path(ev_path).read_text())
    init_db()
    if "--refresh" in sys.argv:  # a fresh machine: load the instrument list, sectors and latest exchange prices first
        jobs.refresh_instruments()
        jobs.refresh_sectors()
        jobs.refresh_prices()
    with SessionLocal() as s:
        rows, as_of = build_rows(s)
        from datetime import date as _date
        from sqlalchemy import select
        days = {_date.fromisoformat(str(r["price_date"])[:10]) for r in rows if r["price_date"]}
        ohlc = {p.instrument_key + "|" + p.trade_date.isoformat(): {"open": p.open, "high": p.high, "low": p.low}
                for p in s.scalars(select(DailyPrice).where(DailyPrice.trade_date.in_(days)))}
    for r in rows:
        r.update(ohlc.get(f"{r['key']}|{str(r['price_date'])[:10]}", {}))
    cards = load_cards(cards_dir)
    nifty = candles("NSE_INDEX|Nifty 50", {}, fetch=True)
    # Candles for the most traded stocks (cached by the hourly refresh; fetched here if missing)
    liquid = sorted([r for r in rows if r["close"]], key=lambda r: -(r["turnover"] or 0))[:600]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(3) as ex:
        got = dict(zip([r["key"] for r in liquid], ex.map(lambda r: candles(r["key"], r, fetch=True), liquid)))
    ind_imp: dict[str, list] = {}
    for e in ev["events"]:
        for ind, (v, why) in e.get("industries", {}).items():
            ind_imp.setdefault(ind, []).append((v, why, e["title"], bool(e.get("exporters_only"))))
    EXPORT = re.compile(r"export|united states|\busa\b|u\.s\.|north america|overseas customers", re.I)
    stock_imp = ev.get("stocks", {})

    out = []
    for r in rows:
        if not r["close"] or (r["turnover"] or 0) < 5e7:  # at least ₹5 crore traded: liquid enough to matter
            continue
        c = got.get(r["key"]) or candles(r["key"], r)
        card = cards.get(r["isin"])
        if len(c) < 120 and not card:
            continue
        x = indicators.compute(c[-400:], nifty) if len(c) >= 120 else {"available": False}
        ts, pro, con = indicators.score(x)
        pat = patterns.detect(c[-250:]) if len(c) >= 120 else {"dow": None, "patterns": []}
        ind = (card or {}).get("industry") or r.get("industry")
        desc = ((card or {}).get("profile") or {}).get("description") or ""
        exporter = bool(EXPORT.search(desc))
        news_items = [{"impact": v, "why": why, "event": t} for v, why, t, exp_only in ind_imp.get(ind, []) if not exp_only or exporter]
        if r["symbol"] in stock_imp:
            v, why, srcs = stock_imp[r["symbol"]]
            news_items.append({"impact": v, "why": why, "event": "Company news", "sources": srcs})
        nsum = max(-3.0, min(3.0, sum(n["impact"] for n in news_items)))
        news_score = round(50 + nsum * 50 / 3)
        fund = (card or {}).get("composite")
        parts = [(W_FUND, fund), (W_TECH, ts), (W_NEWS, news_score)]
        have = [(w, v) for w, v in parts if v is not None]
        combined = round(sum(w * v for w, v in have) / sum(w for w, _ in have)) if have else None
        st = (card or {}).get("st") or {}
        vm = (card or {}).get("vm") or {}
        out.append({
            "isin": r["isin"], "symbol": r["symbol"], "name": r["name"], "industry": ind, "price": r["close"], "change_pct": r["change_pct"],
            "turnover_cr": round((r["turnover"] or 0) / 1e7, 1),
            "fund": fund, "grade": (card or {}).get("grade"), "tech": ts, "news": news_score, "combined": combined,
            "news_items": news_items, "tech_for": pro[:5], "tech_against": con[:4],
            "ind": {k: x.get(k) for k in ("rsi", "adx", "sma50", "sma200", "rs_3m", "atr_pct", "volume_ratio", "from_52w_high_pct", "support", "resistance",
                                           "extended_atr", "supertrend_up", "squeeze")} if x.get("available") else None,
            "dow": (pat.get("dow") or {}).get("trend"), "dow_break": (pat.get("dow") or {}).get("break"),
            "patterns": [{k: p[k] for k in ("pattern", "status", "breakout", "measured_move")} for p in pat.get("patterns", []) if "forming" in p["status"] or "confirm" in p["status"] or "broke" in p["status"]],
            "valuation": vm.get("summary"), "cycle": (vm.get("cycle") or {}).get("stage"),
            "piotroski": (st.get("piotroski") or {}).get("score"), "flags": [f["text"] for f in st.get("checks", []) if f["flag"] == "bad"][:2],
            "mf_rank": ((card or {}).get("magic_formula") or {}).get("rank"),
        })

    def strong_fund(x):
        return x["fund"] is not None and x["fund"] >= 62
    investing = sorted([x for x in out if strong_fund(x) and x["news"] >= 45 and (x["tech"] is None or x["tech"] >= 35)],
                       key=lambda x: -(0.65 * x["fund"] + 0.15 * (x["tech"] or 50) + 0.20 * x["news"]))[:20]
    trading = sorted([x for x in out if x["tech"] is not None and x["tech"] >= 70 and (x["fund"] is None or x["fund"] >= 50) and x["news"] >= 45 and x["turnover_cr"] >= 20
                      and (x["ind"] or {}).get("extended_atr", 0) is not None and (x["ind"] or {}).get("extended_atr", 0) <= 4],
                     key=lambda x: -(0.6 * x["tech"] + 0.2 * (x["fund"] or 50) + 0.2 * x["news"]))[:20]
    caution = sorted([x for x in out if (x["news"] <= 35 and x["turnover_cr"] >= 20) or (x["dow_break"] and x["turnover_cr"] >= 50) or (x["tech"] is not None and x["tech"] <= 20 and x["turnover_cr"] >= 100)],
                     key=lambda x: (x["news"], x["tech"] or 50))[:20]
    sectors = []
    for ind, items in sorted(ind_imp.items(), key=lambda kv: sum(v for v, *_ in kv[1])):
        sectors.append({"industry": ind, "net": round(sum(v for v, *_ in items), 1), "items": [{"impact": v, "why": w, "event": t, "exporters_only": e} for v, w, t, e in items]})
    brief = {"date": ev["date"], "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "prices_as_of": as_of,
             "summary": ev["summary"], "events": ev["events"], "sectors": sectors,
             "investing": investing, "trading": trading, "caution": caution, "universe": len(out),
             "method": f"Each liquid stock (≥ ₹5 crore traded) is scored on fundamentals (the precomputed scorecard: quality incl. Piotroski, value on the industry's methods, growth, ownership, economy), "
                       f"technicals (trend: 50/200-day averages and slope, ADX/DI, Supertrend, Dow structure; momentum: RSI, MACD, 3-month strength vs the Nifty; volume: OBV; stretch above the 50-day average in ATRs) "
                       f"and today's news (industry and company impacts, −2 to +2, judged from the news with sources). Investing list: fundamental score ≥ 62, news not against it, chart not broken. "
                       f"Trading list: technical score ≥ 70, not stretched more than 4 ATRs above the 50-day average, fundamentals not weak, news not against it.",
             "label": "Screening output from published data and today's news. Not investment advice; no position sizes or strikes. Check each name yourself."}
    Path(out_path).write_text(json.dumps(brief, default=str))
    raw = json.dumps(brief, default=str).encode()
    Path(out_path + ".db.json").write_text(json.dumps({"z": base64.b64encode(gzip.compress(raw, 9)).decode(), "date": ev["date"]}))
    print(f"brief: {len(out)} stocks scored; investing {len(investing)}, trading {len(trading)}, caution {len(caution)}")


if __name__ == "__main__":
    main()
